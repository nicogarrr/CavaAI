from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

import main
from app.core import auth as auth_module
from app.core.database import SessionLocal, init_db
from app.models import Tenant
from tests.auth_helpers import auth_settings, bound_headers

SECRET = "tenant-status-test-secret-at-least-32-characters"


@pytest.mark.parametrize(
    ("status", "expected_status_code"),
    [("active", 200), ("suspended", 403), ("deleted", 403)],
)
def test_signed_principal_requires_active_tenant(
    monkeypatch, status, expected_status_code
):
    init_db()
    suffix = uuid4().hex[:8]
    tenant_external_id = f"status-{status}-{suffix}"
    monkeypatch.setattr(
        auth_module,
        "get_settings",
        lambda: auth_settings(strict=True, secret=SECRET),
    )

    db = SessionLocal()
    db.add(
        Tenant(
            external_id=tenant_external_id,
            name=f"Tenant status {status}",
            status=status,
        )
    )
    db.commit()
    db.close()

    try:
        response = TestClient(main.app).get(
            "/api/memory/claims",
            headers=bound_headers(
                SECRET,
                tenant_external_id,
                f"status-user-{tenant_external_id}",
                method="GET",
                path="/api/memory/claims",
            ),
        )

        assert response.status_code == expected_status_code
    finally:
        db = SessionLocal()
        tenant_ids = db.scalars(
            select(Tenant.id).where(Tenant.external_id == tenant_external_id)
        ).all()
        if tenant_ids:
            db.execute(delete(Tenant).where(Tenant.id.in_(tenant_ids)))
            db.commit()
        db.close()
