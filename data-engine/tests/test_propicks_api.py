"""ProPicks funnel API: signed run creation, listing and detail."""

from __future__ import annotations

import time
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

import main
from app.core import auth as auth_module
from app.core.auth import sign_research_identity
from app.core.database import SessionLocal, init_db
from app.models import (
    CalculatedMetric,
    Company,
    FinancialFact,
    ProPickCandidate,
    ProPickRun,
    Tenant,
)

SECRET = "propicks-api-test-secret-at-least-32-chars"


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
            is_production=False,
            research_auth_required=True,
            research_auth_secret=SECRET,
            research_auth_max_age_seconds=300,
        ),
    )


def _seed_company(db, tenant_id: int, ticker: str, roic: str, cfroi: str) -> Company:
    company = Company(
        ticker=ticker,
        name=f"{ticker} Co",
        exchange="TEST",
        currency="USD",
        sector="Industrials",
        industry="Test",
        company_type="standard",
        valuation_model="standard_dcf",
        special_sources=[],
        special_risks=[],
        factor_tags=[],
    )
    db.add(company)
    db.flush()
    metrics = {
        "roic": roic,
        "cfroi_approx": cfroi,
        "wacc": "0.08",
        "fcf_margin_5y": "0.12",
        "owner_earnings_5y": "100",
        "roe_5y": "0.18",
        "net_margin_5y": "0.15",
        "roa_5y": "0.10",
        "capex_to_da_5y": "1.0",
        "quality_moat_score_v2": "0.7",
        "net_debt_to_ebitda": "1.0",
        "fcf_conversion": "0.9",
    }
    for metric, value in metrics.items():
        db.add(
            CalculatedMetric(
                company_id=company.id,
                metric=metric,
                value=Decimal(value),
                unit="decimal",
                period="FY2025",
                fiscal_year=2025,
                status="ok",
                definition_version="test-v1",
                formula=metric,
                source_fact_ids=[],
                calculation_trace={},
                confidence=Decimal("0.9"),
                tenant_id=tenant_id,
            )
        )
    for year in range(2021, 2026):
        for metric, value in (("net_income", "100"), ("revenue", str(900 + year))):
            db.add(
                FinancialFact(
                    company_id=company.id,
                    metric=metric,
                    value=Decimal(value),
                    unit="USD",
                    period=f"FY{year}",
                    fiscal_year=year,
                    fiscal_quarter="FY",
                    source_type="sec_filing",
                    confidence=Decimal("0.95"),
                    tenant_id=tenant_id,
                )
            )
    return company


def test_propicks_run_endpoints(required_auth):
    init_db()
    suffix = uuid4().hex[:8]
    tenant_ext = f"propicks-{suffix}"
    db = SessionLocal()
    tenant = Tenant(external_id=tenant_ext, name="ProPicks test")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    good = _seed_company(db, tenant.id, f"GOOD{suffix[:4]}", "0.20", "0.16")
    bad = _seed_company(db, tenant.id, f"BADD{suffix[:4]}", "0.01", "0.01")
    db.commit()
    good_id, bad_id = good.id, bad.id
    db.close()

    client = TestClient(main.app)
    headers = _headers(tenant_ext, "propicks-test-user")

    created = client.post("/api/propicks/runs", headers=headers)
    assert created.status_code == 201, created.text
    run = created.json()
    # The test app DB is shared: other suites' companies may exist.
    assert run["universe_size"] >= 2

    listed = client.get("/api/propicks/runs", headers=headers)
    assert listed.status_code == 200
    assert any(r["id"] == run["id"] for r in listed.json())

    detail = client.get(f"/api/propicks/runs/{run['id']}", headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    ours = [c for c in body["candidates"] if c["company_id"] == good_id]
    assert len(ours) == 1
    winner = ours[0]
    assert winner["rank"] and winner["rank"] >= 1
    assert winner["coverage"]["roic"] == "ok"
    assert all(c["company_id"] != bad_id for c in body["candidates"])

    full = client.get(
        f"/api/propicks/runs/{run['id']}?only_passed=false", headers=headers
    )
    assert full.status_code == 200
    full_ids = {c["company_id"] for c in full.json()["candidates"]}
    assert {good_id, bad_id} <= full_ids

    missing = client.get("/api/propicks/runs/999999999", headers=headers)
    assert missing.status_code == 404

    unsigned = TestClient(main.app).get("/api/propicks/runs")
    assert unsigned.status_code == 401

    db = SessionLocal()
    db.execute(delete(ProPickCandidate).where(ProPickCandidate.run_id == run["id"]))
    db.execute(delete(ProPickRun).where(ProPickRun.id == run["id"]))
    for cid in (good_id, bad_id):
        db.execute(delete(CalculatedMetric).where(CalculatedMetric.company_id == cid))
        db.execute(delete(FinancialFact).where(FinancialFact.company_id == cid))
        db.execute(delete(Company).where(Company.id == cid))
    db.execute(delete(Tenant).where(Tenant.id == tenant.id))
    db.commit()
    db.close()
