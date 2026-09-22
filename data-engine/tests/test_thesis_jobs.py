"""W7a: async thesis generation jobs — enqueue idempotency, honest phases,
failure classification, duplicate-delivery safety, status endpoint."""

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


def _enqueue_without_dispatch(monkeypatch, ticker="AAPL", force=False):
    import app.workers.dramatiq_app as workers

    monkeypatch.setattr(workers.generate_thesis_job, "send", lambda run_id: None)
    db = SessionLocal()
    try:
        return jobs.enqueue_generation(db, ticker, force)
    finally:
        db.close()


def test_enqueue_is_idempotent_while_active(monkeypatch):
    run1, created1 = _enqueue_without_dispatch(monkeypatch)
    run2, created2 = _enqueue_without_dispatch(monkeypatch)
    assert created1 is True and created2 is False
    assert run1.id == run2.id
    assert run1.status == "queued"
    assert run1.input_payload == {"ticker": "AAPL", "force": False}
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
    assert "SEC timeout" in stored.error_message
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
