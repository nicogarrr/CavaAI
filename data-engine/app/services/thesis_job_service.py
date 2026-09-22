"""Async thesis generation jobs (user preference 2026-09-22: generation may
take longer and run in the background; quality/provenance over latency).

Contract:
- POST /api/thesis/generate-async enqueues a durable job on the workflow-run
  envelope and returns 202 immediately.
- GET /api/thesis/jobs/{id} exposes the HONEST state: queued/running with the
  real current phase (recorded when the generator actually enters it),
  succeeded/failed with timestamps. No invented ETAs anywhere.
- Idempotent enqueue: same ticker+force while a job is active returns the
  existing job instead of duplicating work.
- Retry-safe: ThesisService.generate is atomic and fingerprint-idempotent, so
  a Dramatiq retry resumes safely; re-entry guards prevent double runs.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.entities import WorkflowRun, WorkflowStepRun

WORKFLOW_NAME = "GenerateThesisWorkflow"
ACTIVE_STATUSES = ("queued", "running")

# Real phases instrumented inside ThesisService._generate_atomic. Order matters.
THESIS_PHASES: tuple[str, ...] = (
    "collect_evidence",
    "build_fundamental_model",
    "run_valuation",
    "persist_valuation_snapshot",
    "source_audit",
    "compose_thesis",
    "persist_thesis",
)


def idempotency_key_for(ticker: str, force: bool) -> str:
    return f"thesis-gen:{ticker.upper()}:{bool(force)}"


def enqueue_generation(db: Session, ticker: str, force: bool = False) -> tuple[WorkflowRun, bool]:
    """Return (run, created). created=False when an active job already exists."""
    key = idempotency_key_for(ticker, force)
    existing = db.scalar(
        select(WorkflowRun)
        .where(
            WorkflowRun.workflow_name == WORKFLOW_NAME,
            WorkflowRun.idempotency_key == key,
            WorkflowRun.status.in_(ACTIVE_STATUSES),
        )
        .order_by(desc(WorkflowRun.id))
        .limit(1)
    )
    if existing:
        return existing, False
    run = WorkflowRun(
        workflow_name=WORKFLOW_NAME,
        execution_mode="async_dramatiq",
        status="queued",
        idempotency_key=key,
        input_payload={"ticker": ticker.upper(), "force": bool(force)},
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    # Import lazily: the worker module pulls dramatiq; keep the service importable without it.
    from app.workers.dramatiq_app import generate_thesis_job

    generate_thesis_job.send(run.id)
    return run, True


def job_payload(run: WorkflowRun) -> dict:
    """Honest status payload: real phases and timestamps, never an ETA."""
    steps = sorted(run.steps or [], key=lambda s: s.position)
    return {
        "id": run.id,
        "workflow_name": run.workflow_name,
        "status": run.status,
        "ticker": (run.input_payload or {}).get("ticker"),
        "force": (run.input_payload or {}).get("force"),
        "phases": [
            {
                "name": s.step_name,
                "status": s.status,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "finished_at": s.finished_at.isoformat() if s.finished_at else None,
            }
            for s in steps
        ],
        "current_phase": next(
            (s.step_name for s in reversed(steps) if s.status == "running"), None
        ),
        "result": run.result_payload,
        "error_class": run.error_class,
        "error_message": run.error_message,
        "attempt": run.attempt,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


def run_thesis_job(run_id: int) -> None:
    """Execute one queued thesis job. Idempotent re-entry: a run that already
    reached a terminal state is left untouched (duplicate delivery safe)."""
    db = SessionLocal()
    try:
        run = db.get(
            WorkflowRun, run_id, execution_options={"include_all_tenants": True}
        )
        if run is None or run.status in ("succeeded", "failed"):
            return
        run.status = "running"
        run.started_at = run.started_at or datetime.now(UTC)
        db.commit()

        state = {"position": 0, "open_step": None}

        def on_phase(name: str) -> None:
            now = datetime.now(UTC)
            previous = state["open_step"]
            if previous is not None:
                previous.status = "succeeded"
                previous.finished_at = now
            state["position"] += 1
            step = WorkflowStepRun(
                run_id=run.id,
                step_name=name,
                position=state["position"],
                status="running",
                started_at=now,
            )
            db.add(step)
            db.commit()
            state["open_step"] = step

        payload = run.input_payload or {}
        try:
            from app.services.thesis_service import ThesisService

            thesis = ThesisService().generate(
                db,
                payload["ticker"],
                force_new_version=payload.get("force", False),
                phase_callback=on_phase,
            )
            if state["open_step"] is not None:
                state["open_step"].status = "succeeded"
                state["open_step"].finished_at = datetime.now(UTC)
            run.status = "succeeded"
            run.result_payload = {
                "thesis_version_id": thesis.id,
                "version": thesis.version,
                "status": thesis.status,
            }
            run.finished_at = datetime.now(UTC)
            db.commit()
        except Exception as exc:  # noqa: BLE001 — clasificar y marcar, nunca ocultar
            db.rollback()
            run = db.get(WorkflowRun, run_id, execution_options={"include_all_tenants": True})
            if run is not None:
                if state["open_step"] is not None:
                    step = db.get(WorkflowStepRun, state["open_step"].id)
                    if step is not None and step.status == "running":
                        step.status = "failed"
                        step.error_class = type(exc).__name__
                        step.finished_at = datetime.now(UTC)
                run.status = "failed"
                run.error_class = type(exc).__name__
                run.error_message = str(exc)[:900]
                run.finished_at = datetime.now(UTC)
                db.commit()
            raise
    finally:
        db.close()
