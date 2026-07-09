from types import SimpleNamespace
import time
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

import main
from app.core import auth as auth_module
from app.core.auth import sign_research_identity
from app.core.database import SessionLocal, init_db
from app.models import Claim, Tenant
from app.seed import seed


def _headers(secret: str, tenant_id: str, user_id: str) -> dict[str, str]:
    timestamp = str(int(time.time()))
    return {
        "X-CavaAI-Tenant": tenant_id,
        "X-CavaAI-User": user_id,
        "X-CavaAI-Timestamp": timestamp,
        "X-CavaAI-Signature": sign_research_identity(
            secret,
            tenant_id=tenant_id,
            user_id=user_id,
            timestamp=timestamp,
        ),
    }


def test_signed_tenants_cannot_read_each_others_claims(monkeypatch):
    init_db()
    seed()
    secret = "tenant-test-secret-with-at-least-32-characters"
    monkeypatch.setattr(
        auth_module,
        "get_settings",
        lambda: SimpleNamespace(
            app_env="local",
            research_auth_required=True,
            research_auth_secret=secret,
            research_auth_max_age_seconds=300,
        ),
    )
    suffix = uuid4().hex[:8]
    tenant_a = f"tenant-a-{suffix}"
    tenant_b = f"tenant-b-{suffix}"
    statement_a = f"Tenant A private claim {suffix}"
    statement_b = f"Tenant B private claim {suffix}"
    client = TestClient(main.app)

    unauthorized = client.get("/api/memory/claims")
    assert unauthorized.status_code == 401

    created_a = client.post(
        "/api/memory/claims",
        headers=_headers(secret, tenant_a, f"user-a-{suffix}"),
        json={"ticker": "MSFT", "statement": statement_a},
    )
    created_b = client.post(
        "/api/memory/claims",
        headers=_headers(secret, tenant_b, f"user-b-{suffix}"),
        json={"ticker": "MSFT", "statement": statement_b},
    )
    assert created_a.status_code == 200
    assert created_b.status_code == 200

    list_a = client.get(
        "/api/memory/claims",
        headers=_headers(secret, tenant_a, f"user-a-{suffix}"),
    )
    list_b = client.get(
        "/api/memory/claims",
        headers=_headers(secret, tenant_b, f"user-b-{suffix}"),
    )
    statements_a = {item["statement"] for item in list_a.json()}
    statements_b = {item["statement"] for item in list_b.json()}
    assert statement_a in statements_a
    assert statement_b not in statements_a
    assert statement_b in statements_b
    assert statement_a not in statements_b

    cross_read = client.get(
        f"/api/memory/claims/{created_b.json()['id']}",
        headers=_headers(secret, tenant_a, f"user-a-{suffix}"),
    )
    assert cross_read.status_code == 404

    db = SessionLocal()
    db.execute(
        delete(Claim).where(Claim.statement.in_([statement_a, statement_b]))
    )
    tenant_ids = db.scalars(
        select(Tenant.id).where(
            Tenant.external_id.in_([tenant_a, tenant_b])
        )
    ).all()
    if tenant_ids:
        db.execute(delete(Tenant).where(Tenant.id.in_(tenant_ids)))
    db.commit()
    db.close()
