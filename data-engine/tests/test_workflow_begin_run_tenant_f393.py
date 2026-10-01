"""F393: idempotent replay must work inside a real tenant session."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import Tenant, WorkflowRun
from app.services.workflow_run_service import begin_run


def test_replay_with_active_tenant_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        tenant = Tenant(external_id="f393", name="f393")
        db.add(tenant)
        db.commit()
        db.info["tenant_id"] = tenant.id

        first = begin_run(db, "WF", idempotency_key="k1")
        assert first.replayed is False
        first.finish({"ok": True})

        second = begin_run(db, "WF", idempotency_key="k1")
        assert second.replayed is True
        assert second.run.id == first.run.id
        assert second.run.tenant_id == tenant.id
        assert db.query(WorkflowRun).count() == 1
