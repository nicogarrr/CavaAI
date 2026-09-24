"""W7a: async thesis generation jobs — enqueue idempotency, honest phases,
failure classification, duplicate-delivery safety, status endpoint."""

from datetime import timedelta

import main
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import SessionLocal, init_db
from app.models.entities import WorkflowRun, WorkflowStepRun
from app.seed import seed
from app.services import thesis_job_service as jobs
from app.services.thesis_service import ThesisService


@pytest.fixture(autouse=True)
def _db():
    init_db()
    seed()
    yield
    db = SessionLocal()
    for model in (WorkflowStepRun, WorkflowRun):
        db.query(model).delete()
    db.commit()
    db.close()


def _fake_generate(thesis_id=7):
    def generate(self, db, ticker, force_new_version=False, phase_callback=None):
        for phase in jobs.THESIS_PHASES:
            if phase_callback:
                phase_callback(phase)

        class _T:
            id = thesis_id
            version = 3
            status = "final"

        return _T()

    return generate


def _enqueue_without_dispatch(
    monkeypatch, ticker="AAPL", force=False, *, tenant_id=None, user_id=None,
    send=None,
):
    import app.workers.dramatiq_app as workers

    monkeypatch.setattr(workers.generate_thesis_job, "send", send or (lambda run_id: None))
    db = SessionLocal()
    if tenant_id is not None:
        db.info["tenant_id"] = tenant_id
    if user_id is not None:
        db.info["user_id"] = user_id
    try:
        return jobs.enqueue_generation(db, ticker, force)
    finally:
        db.close()


def test_enqueue_persists_tenant_and_user_context(monkeypatch):
    from app.models import Tenant
    from uuid import uuid4

    external_id = f"thesis-enqueue-tenant-{uuid4().hex[:8]}"
    db = SessionLocal()
    tenant = Tenant(
        external_id=external_id,
        name="Thesis enqueue tenant",
        metadata_={"created_by": "thesis-enqueue-user"},
    )
    db.add(tenant)
    db.commit()
    tenant_id = tenant.id
    db.close()

    try:
        run, created = _enqueue_without_dispatch(
            monkeypatch,
            ticker="AAPL",
            tenant_id=tenant_id,
            user_id="thesis-enqueue-user",
        )

        assert created is True
        assert run.tenant_id == tenant_id
        assert run.input_payload["user_id"] == "thesis-enqueue-user"
    finally:
        db = SessionLocal()
        tenant = db.query(Tenant).filter_by(id=tenant_id).one_or_none()
        if tenant is not None:
            db.delete(tenant)
            db.commit()
        db.close()


def test_enqueue_is_idempotent_while_active(monkeypatch):
    run1, created1 = _enqueue_without_dispatch(monkeypatch)
    run2, created2 = _enqueue_without_dispatch(monkeypatch)
    assert created1 is True and created2 is False
    assert run1.id == run2.id
    assert run1.status == "queued"
    assert run1.input_payload["ticker"] == "AAPL"
    assert run1.input_payload["force"] is False
    assert run1.input_payload["dispatch_sent_at"]
    # force=True is a different key -> a second job may coexist
    run3, created3 = _enqueue_without_dispatch(monkeypatch, force=True)
    assert created3 is True and run3.id != run1.id


def test_run_job_records_real_phases_and_result(monkeypatch):
    monkeypatch.setattr(ThesisService, "generate", _fake_generate())
    run, _ = _enqueue_without_dispatch(monkeypatch)
    jobs.run_thesis_job(run.id)

    db = SessionLocal()
    stored = db.get(WorkflowRun, run.id)
    assert stored.status == "succeeded"
    assert stored.result_payload == {"thesis_version_id": 7, "version": 3, "status": "final"}
    assert stored.started_at and stored.finished_at
    steps = db.scalars(
        select(WorkflowStepRun).where(WorkflowStepRun.run_id == run.id).order_by(WorkflowStepRun.position)
    ).all()
    assert [s.step_name for s in steps] == list(jobs.THESIS_PHASES)
    assert all(s.status == "succeeded" for s in steps)
    db.close()


def test_run_job_failure_marks_failed_and_reraises(monkeypatch):
    def boom(self, db, ticker, force_new_version=False, phase_callback=None):
        if phase_callback:
            phase_callback("collect_evidence")
        raise RuntimeError("SEC timeout")

    monkeypatch.setattr(ThesisService, "generate", boom)
    run, _ = _enqueue_without_dispatch(monkeypatch)
    with pytest.raises(RuntimeError):
        jobs.run_thesis_job(run.id)

    db = SessionLocal()
    stored = db.get(WorkflowRun, run.id)
    assert stored.status == "failed"
    assert stored.error_class == "RuntimeError"
    assert stored.error_message == "Thesis generation failed"
    failed_step = db.scalars(
        select(WorkflowStepRun).where(WorkflowStepRun.run_id == run.id)
    ).first()
    assert failed_step.status == "failed"
    assert failed_step.error_class == "RuntimeError"
    db.close()


def test_duplicate_delivery_after_terminal_is_noop(monkeypatch):
    monkeypatch.setattr(ThesisService, "generate", _fake_generate())
    run, _ = _enqueue_without_dispatch(monkeypatch)
    jobs.run_thesis_job(run.id)
    jobs.run_thesis_job(run.id)  # duplicate delivery: no re-execution, no error

    db = SessionLocal()
    stored = db.get(WorkflowRun, run.id)
    assert stored.status == "succeeded"
    assert db.query(WorkflowStepRun).filter_by(run_id=run.id).count() == len(jobs.THESIS_PHASES)
    db.close()


def test_enqueue_retry_state_is_reused(monkeypatch):
    run, _ = _enqueue_without_dispatch(monkeypatch, ticker="RETRYING")
    db = SessionLocal()
    stored = db.get(WorkflowRun, run.id)
    stored.status = "retrying"
    stored.attempt = 1
    db.commit()
    db.close()

    replay, created = _enqueue_without_dispatch(monkeypatch, ticker="RETRYING")
    assert created is False
    assert replay.id == run.id


def test_status_endpoint_payload(monkeypatch):
    monkeypatch.setattr(ThesisService, "generate", _fake_generate())
    run, _ = _enqueue_without_dispatch(monkeypatch)
    jobs.run_thesis_job(run.id)

    client = TestClient(main.app)
    response = client.get(f"/api/thesis/jobs/{run.id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "succeeded"
    assert payload["ticker"] == "AAPL"
    assert len(payload["phases"]) == len(jobs.THESIS_PHASES)
    assert payload["current_phase"] is None
    assert payload["result"]["thesis_version_id"] == 7
    assert "estimated" not in str(payload).lower()  # no invented ETAs
    assert client.get("/api/thesis/jobs/999999").status_code == 404


def test_enqueue_returns_succeeded_run_without_unique_key_error(monkeypatch):
    run, _ = _enqueue_without_dispatch(monkeypatch, ticker="TERMINAL")
    db = SessionLocal()
    stored = db.get(WorkflowRun, run.id)
    stored.status = "succeeded"
    db.commit()
    db.close()

    replay, created = _enqueue_without_dispatch(monkeypatch, ticker="TERMINAL")

    assert created is False
    assert replay.id == run.id
    assert replay.status == "succeeded"


def test_failed_run_is_redispatched_on_retry(monkeypatch):
    """El front dice "puedes reintentar": un run fallido no es un resultado
    reutilizable - re-postear el mismo ticker debe re-despachar el run."""
    sent: list[int] = []
    run, _ = _enqueue_without_dispatch(monkeypatch, ticker="RETRY")
    db = SessionLocal()
    stored = db.get(WorkflowRun, run.id)
    stored.status = "failed"
    stored.error_class = "ValueError"
    stored.error_message = "Thesis generation failed"
    db.commit()
    db.close()

    replay, created = _enqueue_without_dispatch(
        monkeypatch, ticker="RETRY", send=lambda run_id: sent.append(run_id)
    )

    assert created is False
    assert replay.id == run.id
    assert replay.status == "queued"
    assert replay.error_class is None
    assert replay.error_message is None
    assert sent == [run.id]
    assert (replay.input_payload or {}).get("attempt") == 2


def test_generate_async_ensures_company_stub(monkeypatch):
    """El buscador resuelve tickers via Finnhub sin ficha en BD; generate-async
    debe crear la ficha para que la generacion no muera con Unknown ticker."""
    import app.workers.dramatiq_app as workers

    monkeypatch.setattr(workers.generate_thesis_job, "send", lambda run_id: None)

    def fail_enrich(self, db, company):
        raise ConnectionError("sin red en el test")

    monkeypatch.setattr(
        "app.services.company_enrichment_service.CompanyEnrichmentService.enrich",
        fail_enrich,
    )
    client = TestClient(main.app)
    response = client.post(
        "/api/thesis/generate-async",
        json={"ticker": "ZZTEST", "force_new_version": False},
    )
    assert response.status_code == 202
    db = SessionLocal()
    from app.models import Company

    company = db.scalar(select(Company).where(Company.ticker == "ZZTEST"))
    assert company is not None
    db.delete(company)
    db.commit()
    db.close()


def test_failed_dispatch_is_recoverable(monkeypatch):
    import app.workers.dramatiq_app as workers

    def fail_send(_run_id):
        raise ConnectionError("redis unavailable")

    monkeypatch.setattr(workers.generate_thesis_job, "send", fail_send)
    run, created = _enqueue_without_dispatch(
        monkeypatch, ticker="DISPATCH", send=fail_send
    )
    assert created is True
    assert run.status == "dispatch_failed"

    sent: list[int] = []
    replay, replay_created = _enqueue_without_dispatch(
        monkeypatch, ticker="DISPATCH", send=lambda run_id: sent.append(run_id)
    )

    assert replay_created is False
    assert replay.id == run.id
    assert replay.status == "queued"
    assert sent == [run.id]


def test_expired_running_delivery_is_recovered(monkeypatch):
    monkeypatch.setattr(ThesisService, "generate", _fake_generate())
    run, _ = _enqueue_without_dispatch(monkeypatch, ticker="STALE")
    db = SessionLocal()
    stored = db.get(WorkflowRun, run.id)
    stored.status = "running"
    stored.started_at = stored.created_at - jobs.RUNNING_LEASE - timedelta(minutes=1)
    db.commit()
    db.close()

    jobs.run_thesis_job(run.id)

    db = SessionLocal()
    recovered = db.get(WorkflowRun, run.id)
    assert recovered.status == "succeeded"
    assert recovered.attempt >= 2
    db.close()


def test_queued_run_without_dispatch_marker_is_recoverable(monkeypatch):
    run, _ = _enqueue_without_dispatch(monkeypatch, ticker="QUEUED_RECOVER")
    db = SessionLocal()
    stored = db.get(WorkflowRun, run.id)
    payload = dict(stored.input_payload or {})
    payload.pop("dispatch_sent_at", None)
    stored.input_payload = payload
    db.commit()
    db.close()

    sent: list[int] = []
    replay, created = _enqueue_without_dispatch(
        monkeypatch, ticker="QUEUED_RECOVER", send=lambda run_id: sent.append(run_id)
    )
    assert created is False
    assert replay.id == run.id
    assert sent == [run.id]
    assert replay.input_payload["dispatch_sent_at"]


def test_same_ticker_key_is_scoped_by_tenant(monkeypatch):
    from app.models import Tenant
    from uuid import uuid4

    ids = []
    db = SessionLocal()
    for label in ("A", "B"):
        tenant = Tenant(
            external_id=f"thesis-scope-{label}-{uuid4().hex[:8]}",
            name=f"Tenant {label}",
            metadata_={"created_by": f"user-{label}"},
        )
        db.add(tenant)
        db.flush()
        ids.append(tenant.id)
    db.commit()
    db.close()
    try:
        run_a, created_a = _enqueue_without_dispatch(
            monkeypatch, ticker="SCOPED", tenant_id=ids[0], user_id="user-A"
        )
        run_b, created_b = _enqueue_without_dispatch(
            monkeypatch, ticker="SCOPED", tenant_id=ids[1], user_id="user-B"
        )
        assert created_a and created_b
        assert run_a.id != run_b.id
    finally:
        db = SessionLocal()
        db.query(WorkflowRun).filter(WorkflowRun.id.in_([run_a.id, run_b.id])).delete(synchronize_session=False)
        db.query(Tenant).filter(Tenant.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
        db.close()
