from types import SimpleNamespace
import time
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import delete, select

import main
from app.core import auth as auth_module
from app.core.auth import sign_research_identity
from app.core.database import SessionLocal, init_db
from app.models import Tenant

SECRET = "tenant-status-test-secret-at-least-32-characters"


def _headers(tenant_external_id: str) -> dict[str, str]:
    timestamp = str(int(time.time()))
    user_id = f"status-user-{tenant_external_id}"
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
        lambda: SimpleNamespace(
            app_env="test",
            is_production=False,
            research_auth_required=True,
            research_auth_secret=SECRET,
            research_auth_max_age_seconds=300,
        ),
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
            "/api/memory/claims", headers=_headers(tenant_external_id)
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
