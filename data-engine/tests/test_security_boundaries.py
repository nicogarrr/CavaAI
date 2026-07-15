from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
import time
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import delete, select

import main
from app.core import auth as auth_module
from app.core.auth import sign_research_identity
from app.core.config import Settings
from app.core.database import SessionLocal, init_db
from app.models import Claim, Company, Document, DocumentChunk, FinancialFact, MemoryItem, Tenant
from app.seed import seed
from app.services.financial_ingestion_service import FinancialIngestionService
from app.workers import dramatiq_app


SECRET = "research-security-test-secret-at-least-32-chars"


def _headers(tenant_external_id: str, user_id: str) -> dict[str, str]:
    timestamp = str(int(time.time()))
    return {
        "X-CavaAI-Tenant": tenant_external_id,
        "X-CavaAI-User": user_id,
        "X-CavaAI-Timestamp": timestamp,
        "X-CavaAI-Signature": sign_research_identity(
            SECRET,
            tenant_id=tenant_external_id,
            user_id=user_id,
            timestamp=timestamp,
        ),
    }


@pytest.fixture
def required_auth(monkeypatch):
    monkeypatch.setattr(
        auth_module,
        "get_settings",
        lambda: SimpleNamespace(
            app_env="test",
            research_auth_required=True,
            research_auth_secret=SECRET,
            research_auth_max_age_seconds=300,
        ),
    )


def test_research_auth_settings_are_real_and_private_by_default(monkeypatch):
    monkeypatch.delenv("RESEARCH_AUTH_REQUIRED", raising=False)
    settings = Settings(_env_file=None)
    assert settings.research_auth_required is True
    assert settings.research_auth_secret is None
    assert settings.research_auth_max_age_seconds == 300

    configured = Settings(
        _env_file=None,
        research_auth_required=True,
        research_auth_secret=SECRET,
        research_auth_max_age_seconds=120,
    )
    assert configured.research_auth_secret == SECRET
    assert configured.research_auth_max_age_seconds == 120


def test_worker_session_requires_and_preserves_tenant_and_user():
    init_db()
    suffix = uuid4().hex[:8]
    db = SessionLocal()
    tenant = Tenant(
        external_id=f"worker-{suffix}",
        name="Worker tenant",
        metadata_={"created_by": f"worker-user-{suffix}"},
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    tenant_id = tenant.id
    db.close()

    with pytest.raises(ValueError, match="tenant_id and user_id"):
        dramatiq_app._session(None, None)

    scoped = dramatiq_app._session(tenant_id, f"worker-user-{suffix}")
    try:
        assert scoped.info == {
            "tenant_id": tenant_id,
            "user_id": f"worker-user-{suffix}",
        }
    finally:
        scoped.close()

    assert (tenant_id, f"worker-user-{suffix}") in dramatiq_app.tenant_contexts()

    db = SessionLocal()
    db.execute(delete(Tenant).where(Tenant.id == tenant_id))
    db.commit()
    db.close()


def test_worker_memory_consolidation_cannot_touch_another_tenant():
    init_db()
    suffix = uuid4().hex[:8]
    db = SessionLocal()
    tenants = [
        Tenant(
            external_id=f"memory-{name}-{suffix}",
            name=f"Tenant {name}",
            metadata_={"created_by": f"user-{name}-{suffix}"},
        )
        for name in ("a", "b")
    ]
    db.add_all(tenants)
    db.commit()
    for tenant in tenants:
        db.refresh(tenant)
        db.add_all(
            [
                MemoryItem(
                    tenant_id=tenant.id,
                    scope="portfolio",
                    memory_type="note",
                    content=f"Duplicate memory {suffix}",
                    status="active",
                ),
                MemoryItem(
                    tenant_id=tenant.id,
                    scope="portfolio",
                    memory_type="note",
                    content=f" duplicate   memory {suffix} ",
                    status="active",
                ),
            ]
        )
    db.commit()
    tenant_a_id, tenant_b_id = (tenant.id for tenant in tenants)
    db.close()

    result = dramatiq_app.consolidate_memory.fn(
        tenant_a_id,
        f"user-a-{suffix}",
    )
    assert result["status"] == "ok"
    assert result["duplicates_consolidated"] == 1

    db = SessionLocal()
    rows_a = db.scalars(
        select(MemoryItem)
        .where(MemoryItem.tenant_id == tenant_a_id)
        .execution_options(include_all_tenants=True)
    ).all()
    rows_b = db.scalars(
        select(MemoryItem)
        .where(MemoryItem.tenant_id == tenant_b_id)
        .execution_options(include_all_tenants=True)
    ).all()
    assert sorted(item.status for item in rows_a) == ["active", "consolidated"]
    assert [item.status for item in rows_b] == ["active", "active"]
    db.execute(delete(MemoryItem).where(MemoryItem.tenant_id.in_([tenant_a_id, tenant_b_id])))
    db.execute(delete(Tenant).where(Tenant.id.in_([tenant_a_id, tenant_b_id])))
    db.commit()
    db.close()


def test_financial_replacement_delete_is_tenant_scoped():
    init_db()
    seed()
    suffix = uuid4().hex[:8]
    db = SessionLocal()
    company = db.scalar(select(Company).where(Company.ticker == "MSFT"))
    assert company is not None
    tenants = [
        Tenant(external_id=f"facts-{name}-{suffix}", name=f"Facts {name}")
        for name in ("a", "b")
    ]
    db.add_all(tenants)
    db.commit()
    for tenant in tenants:
        db.refresh(tenant)
        db.add(
            FinancialFact(
                tenant_id=tenant.id,
                company_id=company.id,
                metric=f"tenant_delete_probe_{suffix}",
                value=Decimal("1"),
                unit="USD",
                period=f"FY-{suffix}",
                source_type="SEC",
            )
        )
    db.commit()
    tenant_a_id, tenant_b_id = (tenant.id for tenant in tenants)
    company_id = company.id
    db.close()

    scoped = SessionLocal()
    scoped.info["tenant_id"] = tenant_a_id
    scoped.info["user_id"] = f"user-a-{suffix}"
    company = scoped.get(Company, company_id)
    assert company is not None
    FinancialIngestionService()._replace_sec_data(scoped, company)
    scoped.commit()
    scoped.close()

    db = SessionLocal()
    probes = db.scalars(
        select(FinancialFact)
        .where(FinancialFact.metric == f"tenant_delete_probe_{suffix}")
        .execution_options(include_all_tenants=True)
    ).all()
    assert [(fact.tenant_id, fact.value) for fact in probes] == [
        (tenant_b_id, Decimal("1.000000"))
    ]
    db.execute(delete(FinancialFact).where(FinancialFact.metric == f"tenant_delete_probe_{suffix}"))
    db.execute(delete(Tenant).where(Tenant.id.in_([tenant_a_id, tenant_b_id])))
    db.commit()
    db.close()


def test_cross_tenant_document_chunk_cannot_be_linked_as_evidence(required_auth):
    init_db()
    seed()
    suffix = uuid4().hex[:8]
    tenant_a_external = f"chunk-a-{suffix}"
    tenant_b_external = f"chunk-b-{suffix}"
    user_a = f"user-a-{suffix}"
    user_b = f"user-b-{suffix}"
    client = TestClient(main.app)

    claim_response = client.post(
        "/api/memory/claims",
        headers=_headers(tenant_a_external, user_a),
        json={"ticker": "MSFT", "statement": f"Private claim {suffix}"},
    )
    assert claim_response.status_code == 200
    claim_id = claim_response.json()["id"]

    # Create tenant B through the real signed bridge, then attach a private chunk.
    tenant_b_claim = client.post(
        "/api/memory/claims",
        headers=_headers(tenant_b_external, user_b),
        json={"ticker": "MSFT", "statement": f"Tenant B bootstrap {suffix}"},
    )
    assert tenant_b_claim.status_code == 200

    db = SessionLocal()
    tenant_b = db.scalar(select(Tenant).where(Tenant.external_id == tenant_b_external))
    company = db.scalar(select(Company).where(Company.ticker == "MSFT"))
    assert tenant_b is not None and company is not None
    document = Document(
        tenant_id=tenant_b.id,
        company_id=company.id,
        title=f"Tenant B private document {suffix}",
        source_type="manual",
    )
    db.add(document)
    db.flush()
    chunk = DocumentChunk(
        tenant_id=tenant_b.id,
        document_id=document.id,
        chunk_index=0,
        text=f"Private evidence {suffix}",
    )
    db.add(chunk)
    db.commit()
    db.refresh(chunk)
    chunk_id = chunk.id
    document_id = document.id
    tenant_ids = db.scalars(
        select(Tenant.id).where(
            Tenant.external_id.in_([tenant_a_external, tenant_b_external])
        )
    ).all()
    db.close()

    response = client.post(
        f"/api/memory/claims/{claim_id}/evidence",
        headers=_headers(tenant_a_external, user_a),
        json={
            "document_chunk_id": chunk_id,
            "evidence_type": "supports",
            "summary": "Attempted cross-tenant evidence",
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Document chunk not found"

    db = SessionLocal()
    db.execute(delete(DocumentChunk).where(DocumentChunk.id == chunk_id))
    db.execute(delete(Document).where(Document.id == document_id))
    db.execute(delete(Claim).where(Claim.id.in_([claim_id, tenant_b_claim.json()["id"]])))
    db.execute(delete(Tenant).where(Tenant.id.in_(tenant_ids)))
    db.commit()
    db.close()
