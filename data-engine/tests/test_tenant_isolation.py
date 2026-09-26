from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

import main
from app.core import auth as auth_module
from app.core.database import SessionLocal, init_db
from app.models import Claim, Tenant
from app.seed import seed

from tests.auth_helpers import auth_settings, signed_request


def test_signed_tenants_cannot_read_each_others_claims(monkeypatch):
    init_db()
    seed()
    secret = "tenant-test-secret-with-at-least-32-characters"
    monkeypatch.setattr(
        auth_module,
        "get_settings",
        lambda: auth_settings(strict=True, secret=secret, app_env="local"),
    )
    suffix = uuid4().hex[:8]
    tenant_a = f"tenant-a-{suffix}"
    tenant_b = f"tenant-b-{suffix}"
    statement_a = f"Tenant A private claim {suffix}"
    statement_b = f"Tenant B private claim {suffix}"
    client = TestClient(main.app)

    unauthorized = client.get("/api/memory/claims")
    assert unauthorized.status_code == 401

    created_a = signed_request(
        client, secret, tenant_a, f"user-a-{suffix}", "POST", "/api/memory/claims",
        json_body={"ticker": "MSFT", "statement": statement_a},
    )
    created_b = signed_request(
        client, secret, tenant_b, f"user-b-{suffix}", "POST", "/api/memory/claims",
        json_body={"ticker": "MSFT", "statement": statement_b},
    )
    assert created_a.status_code == 200
    assert created_b.status_code == 200

    list_a = signed_request(
        client, secret, tenant_a, f"user-a-{suffix}", "GET", "/api/memory/claims"
    )
    list_b = signed_request(
        client, secret, tenant_b, f"user-b-{suffix}", "GET", "/api/memory/claims"
    )
    statements_a = {item["statement"] for item in list_a.json()}
    statements_b = {item["statement"] for item in list_b.json()}
    assert statement_a in statements_a
    assert statement_b not in statements_a
    assert statement_b in statements_b
    assert statement_a not in statements_b

    cross_read = signed_request(
        client, secret, tenant_a, f"user-a-{suffix}", "GET",
        f"/api/memory/claims/{created_b.json()['id']}",
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
