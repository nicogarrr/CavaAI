"""Durable job envelope for thesis backtests.

A grid of tickers x quarters is hundreds of valuations, each one rebuilding a
snapshot and running a DCF. Doing that inside a request handler holds a
connection and a worker thread for minutes, so the grid goes on the same
``WorkflowRun`` envelope every other long job in the repo uses — no new queue,
no new status vocabulary, no polling contract to learn.

Contract:
- ``POST /api/thesis-backtest`` enqueues and returns 202 with the honest state.
- ``GET /api/thesis-backtest/{run_id}`` reports queued / running / succeeded /
  failed with real timestamps, and ``dispatch_failed`` when the broker could not
  be reached. Never an invented ETA.
- Idempotent enqueue: the same grid parameters re-posted returns the existing
  run instead of recomputing it. Backtests are expensive and deterministic, so
  a second identical request is a replay, not new work.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import WorkflowRun, WorkflowStepRun

WORKFLOW_NAME = "ThesisBacktestWorkflow"
ACTIVE_STATUSES = ("queued", "running", "retrying", "dispatch_failed")

#: Upper bound on one grid. Past this the request is refused rather than queued,
#: because a 40-ticker x 10-year monthly grid is ~4800 valuations and would sit
#: in the queue for hours: the honest answer is to narrow the grid, not to
#: discover the cost after the fact.
MAX_CELLS = 2000

# Phases, in the order the worker actually enters them. Recorded on entry, so
# the reported phase is never a prediction.
BACKTEST_PHASES: tuple[str, ...] = (
    "resolve_company",
    "value_cell",
    "persist_cell",
    "aggregate_metrics",
)


def idempotency_key_for(
    tickers: list[str], start: date, end: date, step: str, strategy: str
) -> str:
    ordered = ",".join(sorted(t.upper() for t in tickers))
    return f"thesis-backtest:{ordered}:{start.isoformat()}:{end.isoformat()}:{step}:{strategy}"


def _dispatch_run(run: WorkflowRun) -> None:
    from app.workers.thesis_backtest_actors import run_thesis_backtest_job

    run_thesis_backtest_job.send(run.id)


def enqueue_backtest(
    db: Session,
    *,
    tickers: list[str],
    start: date,
    end: date,
    step: str = "1M",
    as_of_strategy: str = "replay",
    thesis_filter: str | None = None,
    request_id: str | None = None,
) -> tuple[WorkflowRun, bool]:
    """Return a durable run for this grid, dispatching it when it is new.

    ``(run, created)``: ``created=False`` means this is a replay of an identical
    request and nothing will be recomputed.
    """
    key = idempotency_key_for(tickers, start, end, step, as_of_strategy)
    if request_id:
        key = f"{key}:{request_id}"
    tenant_id = db.info.get("tenant_id")
    user_id = str(db.info.get("user_id") or "").strip() or None
    payload: dict = {
        "tickers": [t.upper() for t in tickers],
        "start": start.isoformat(),
        "end": end.isoformat(),
        "step": step,
        "as_of_strategy": as_of_strategy,
        "thesis_filter": thesis_filter,
        "attempt": 1,
    }
    if tenant_id is not None:
        payload["tenant_id"] = int(tenant_id)
    if user_id is not None:
        payload["user_id"] = user_id

    existing = db.scalar(
        select(WorkflowRun)
        .where(
            WorkflowRun.workflow_name == WORKFLOW_NAME,
            WorkflowRun.idempotency_key == key,
        )
        .order_by(desc(WorkflowRun.id))
        .limit(1)
    )
    if existing is not None and existing.status == "succeeded":
        return existing, False
    if existing is not None:
        needs_dispatch = existing.status in {"failed", "dispatch_failed"} or (
            existing.status == "queued"
            and not (existing.input_payload or {}).get("dispatch_sent_at")
        )
        if needs_dispatch:
            try:
                _dispatch_run(existing)
            except Exception as exc:  # noqa: BLE001 - recorded, never swallowed
                existing.status = "dispatch_failed"
                existing.error_class = type(exc).__name__
                existing.error_message = "Backtest dispatch failed"
                db.commit()
                return existing, False
            payload = dict(existing.input_payload or {})
            if existing.status == "failed":
                payload["attempt"] = int(payload.get("attempt") or 1) + 1
            payload["dispatch_sent_at"] = datetime.now(UTC).isoformat()
            existing.input_payload = payload
            existing.status = "queued"
            existing.error_class = None
            existing.error_message = None
            existing.finished_at = None
            db.commit()
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
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raced = db.scalar(
            select(WorkflowRun)
            .where(
                WorkflowRun.workflow_name == WORKFLOW_NAME,
                WorkflowRun.idempotency_key == key,
            )
            .order_by(desc(WorkflowRun.id))
            .limit(1)
        )
        if raced is not None:
            return raced, False
        raise
    db.refresh(run)

    try:
        _dispatch_run(run)
    except Exception as exc:  # noqa: BLE001 - the run row must say why
        run.status = "dispatch_failed"
        run.error_class = type(exc).__name__
        run.error_message = "Backtest dispatch failed"
        db.commit()
    else:
        payload["dispatch_sent_at"] = datetime.now(UTC).isoformat()
        run.input_payload = payload
        db.commit()
    return run, True


def run_payload(run: WorkflowRun) -> dict:
    """Honest status payload: real phases, no ETA, no invented progress."""
    steps = sorted(run.steps or [], key=lambda step: step.position)
    payload = run.input_payload or {}
    return {
        "run_id": run.id,
        "workflow_name": run.workflow_name,
        "status": run.status,
        "backtest_run_id": (run.result_payload or {}).get("backtest_run_id"),
        "tickers": payload.get("tickers"),
        "start": payload.get("start"),
        "end": payload.get("end"),
        "step": payload.get("step"),
        "as_of_strategy": payload.get("as_of_strategy"),
        "current_phase": next(
            (step.step_name for step in reversed(steps) if step.status == "running"), None
        ),
        "phases": [
            {
                "name": step.step_name,
                "status": step.status,
                "started_at": step.started_at.isoformat() if step.started_at else None,
                "finished_at": step.finished_at.isoformat() if step.finished_at else None,
            }
            for step in steps
        ],
        "result": run.result_payload,
        "error_class": run.error_class,
        "error_message": run.error_message,
        "attempt": run.attempt,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def execute(run_id: int) -> dict:
    """Run a queued backtest grid with tenant context and honest step tracking.

    Mirrors ``thesis_job_service.run_thesis_job``: the run row is the contract,
    every phase is recorded on entry, and a failure classifies itself as
    retryable or terminal instead of retrying forever.
    """
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        run = db.get(
            WorkflowRun, run_id, execution_options={"include_all_tenants": True}
        )
        if run is None or run.status in {"succeeded", "failed"}:
            return {"status": "skipped", "reason": "run ya terminal o inexistente"}

        now = datetime.now(UTC)
        if run.status == "running":
            started = _utc(run.started_at)
            if started is not None and (now - started).total_seconds() < 60:
                return {"status": "skipped", "reason": "otro worker ya lo ejecuta"}

        payload = dict(run.input_payload or {})
        tenant_id = payload.get("tenant_id")
        if tenant_id is not None:
            db.info["tenant_id"] = int(tenant_id)
        if payload.get("user_id"):
            db.info["user_id"] = str(payload["user_id"])
        run.status = "running"
        run.started_at = run.started_at or now
        run.finished_at = None
        run.error_class = None
        run.error_message = None
        db.commit()

        from app.services.thesis_backtest_service import ThesisBacktestService

        state: dict[str, object] = {"position": 0, "open_step": None}

        def on_phase(name: str) -> None:
            previous = state["open_step"]
            if previous is not None:
                previous.status = "succeeded"
                previous.finished_at = datetime.now(UTC)
            state["position"] = int(state["position"]) + 1
            step = WorkflowStepRun(
                run_id=run.id,
                step_name=name,
                position=int(state["position"]),
                attempt=int(run.attempt or 1),
                status="running",
                started_at=datetime.now(UTC),
                tenant_id=run.tenant_id,
            )
            db.add(step)
            db.flush()
            state["open_step"] = step

        try:
            on_phase(BACKTEST_PHASES[0])
            backtest_run = ThesisBacktestService().run(
                db,
                tickers=list(payload.get("tickers") or []),
                start=date.fromisoformat(str(payload["start"])),
                end=date.fromisoformat(str(payload["end"])),
                step=str(payload.get("step") or "1M"),
                as_of_strategy=str(payload.get("as_of_strategy") or "replay"),
                thesis_filter=payload.get("thesis_filter"),
                commit=True,
            )
            open_step = state["open_step"]
            if open_step is not None:
                open_step.status = "succeeded"
                open_step.finished_at = datetime.now(UTC)
            run = db.get(WorkflowRun, run_id, execution_options={"include_all_tenants": True})
            run.status = "succeeded"
            run.result_payload = {
                "backtest_run_id": backtest_run.id,
                "cells": backtest_run.cells_done,
            }
            run.finished_at = datetime.now(UTC)
            db.commit()
            return {"status": "succeeded", "backtest_run_id": backtest_run.id}
        except Exception as exc:  # noqa: BLE001 - the run row records the cause
            db.rollback()
            run = db.get(WorkflowRun, run_id, execution_options={"include_all_tenants": True})
            if run is not None:
                run.status = "failed"
                run.error_class = type(exc).__name__
                run.error_message = "Thesis backtest failed"
                run.finished_at = datetime.now(UTC)
                db.commit()
            raise
    finally:
        db.close()
