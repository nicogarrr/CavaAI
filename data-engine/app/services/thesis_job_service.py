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

from app.core.config import get_settings
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
    """Return (run, created), carrying the authenticated worker context.

    The HTTP response remains unchanged. The context is persisted on the
    durable run so a worker never has to infer ownership from its process
    environment or bypass tenant scoping globally.
    """
    key = idempotency_key_for(ticker, force)
    tenant_id = db.info.get("tenant_id")
    user_id = str(db.info.get("user_id") or "").strip() or None
    payload: dict = {"ticker": ticker.upper(), "force": bool(force)}
    if tenant_id is not None:
        payload["tenant_id"] = int(tenant_id)
    if user_id is not None:
        payload["user_id"] = user_id

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
        tenant_id=tenant_id,
        workflow_name=WORKFLOW_NAME,
        execution_mode="async_dramatiq",
        status="queued",
        idempotency_key=key,
        input_payload=payload,
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


def _is_retryable_error(exc: Exception) -> bool:
    """Classify delivery failures without importing the worker module eagerly."""
    import httpx
    import redis.exceptions as redis_exc
    from sqlalchemy import exc as sa_exc

    if isinstance(
        exc,
        (
            ConnectionError,
            TimeoutError,
            sa_exc.OperationalError,
            sa_exc.TimeoutError,
            redis_exc.RedisError,
            httpx.TimeoutException,
            httpx.TransportError,
        ),
    ):
        return True
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return isinstance(status, int) and (status == 429 or status >= 500)


def run_thesis_job(run_id: int) -> None:
    """Execute one delivery of a thesis job with explicit tenant context.

    A transient failure is recorded as ``retrying`` and re-raised so Dramatiq
    can deliver the next attempt. Only the final failed attempt is terminal.
    Local/test callers without Research auth retain their historical unscoped
    behavior; production and authenticated runs fail closed without context.
    """
    from app.core.config import get_settings

    db = SessionLocal()
    try:
        run = db.get(
            WorkflowRun, run_id, execution_options={"include_all_tenants": True}
        )
        if run is None or run.status in ("succeeded", "failed", "running"):
            return

        settings = get_settings()
        payload = run.input_payload or {}
        tenant_id = payload.get("tenant_id")
        user_id = payload.get("user_id")
        tenant = None
        if tenant_id is not None and user_id:
            from app.models import Tenant

            tenant = db.get(
                Tenant, int(tenant_id), execution_options={"include_all_tenants": True}
            )
        if tenant_id is not None and (tenant is None or tenant.status != "active"):
            run.status = "failed"
            run.error_class = "TenantAccessError"
            run.error_message = "Job tenant is not active"
            run.finished_at = datetime.now(UTC)
            db.commit()
            raise ValueError(run.error_message)
        if (
            settings.research_auth_required or settings.is_production
        ) and (tenant_id is None or not user_id):
            run.status = "failed"
            run.error_class = "MissingTenantContext"
            run.error_message = "Thesis job is missing tenant/user context"
            run.finished_at = datetime.now(UTC)
            db.commit()
            raise ValueError(run.error_message)

        if run.status == "retrying":
            run.attempt = max(int(run.attempt or 1) + 1, 2)
        else:
            run.attempt = max(int(run.attempt or 1), 1)
        run.status = "running"
        run.started_at = run.started_at or datetime.now(UTC)
        run.finished_at = None
        if tenant is not None:
            db.info["tenant_id"] = tenant.id
            db.info["user_id"] = str(user_id)
        db.commit()

        state: dict[str, object] = {"position": 0, "open_step": None}

        def on_phase(name: str) -> None:
            now = datetime.now(UTC)
            previous = state["open_step"]
            if previous is not None:
                previous.status = "succeeded"
                previous.finished_at = now
            state["position"] = int(state["position"]) + 1
            step = WorkflowStepRun(
                run_id=run.id,
                step_name=name,
                position=int(state["position"]),
                attempt=int(run.attempt or 1),
                status="running",
                started_at=now,
                tenant_id=tenant.id if tenant is not None else None,
            )
            db.add(step)
            db.commit()
            state["open_step"] = step

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
            run.error_class = None
            run.error_message = None
            run.finished_at = datetime.now(UTC)
            db.commit()
        except Exception as exc:
            db.rollback()
            run = db.get(WorkflowRun, run_id, execution_options={"include_all_tenants": True})
            retryable = _is_retryable_error(exc)
            if run is not None:
                open_step = state.get("open_step")
                if open_step is not None:
                    step = db.get(WorkflowStepRun, int(open_step.id))
                    if step is not None and step.status == "running":
                        step.status = "retrying" if retryable else "failed"
                        step.error_class = type(exc).__name__
                        step.finished_at = None if retryable else datetime.now(UTC)
                run.error_class = type(exc).__name__
                run.error_message = (
                    "Transient failure; delivery will be retried"
                    if retryable
                    else "Thesis generation failed"
                )
                if retryable and int(run.attempt or 1) < 2:
                    run.status = "retrying"
                else:
                    run.status = "failed"
                    run.finished_at = datetime.now(UTC)
                db.commit()
            raise
    finally:
        db.close()
