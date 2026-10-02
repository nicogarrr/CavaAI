"""API del backtest point-in-time de tesis.

Cuatro endpoints, y una regla que los atraviesa: **ningún fair value se devuelve
sin ``as_of`` y ``evidence_cutoff`` al lado**. Un número de tesis sin la fecha en
que se cortó la evidencia es exactamente el dato que un backtest sin look-ahead
debería impedir mostrar, y el endpoint que lo expone es donde se reintroduciría.

La rejilla no se ejecuta en el request: se encola sobre el mismo envelope
``WorkflowRun`` que usa el resto de trabajos largos del repo y se responde 202.
No hay ETAs inventadas ni progreso estimado; las fases se registran cuando el
worker entra en ellas.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.thesis_backtest_job_service import (
    MAX_CELLS,
    WORKFLOW_NAME,
    enqueue_backtest,
    run_payload,
)
from app.services.thesis_backtest_service import (
    ND,
    ThesisBacktestService,
    build_grid,
)

router = APIRouter()

#: Un ticker con nombre de índice no es una tesis: es la referencia del alpha.
_BENCHMARK_PREFIXES = ("^", "IDX", "Benchmark")

#: Tope de celdas devueltas por `GET /cells`. La rejilla entera se lee con
#: `GET /report`; un endpoint de celdas sin tope es una vía para volcar la tabla.
MAX_PAGE = 500


class BacktestRequest(BaseModel):
    tickers: list[str] = Field(min_length=1, max_length=40)
    start: date
    end: date
    step: str = Field(default="1M", pattern="^(1M|1Q)$")
    as_of_strategy: str = Field(default="replay", pattern="^replay$")
    thesis_filter: str | None = None
    request_id: str | None = None


def _reject_benchmarks(tickers: list[str]) -> None:
    for ticker in tickers:
        upper = ticker.upper()
        if any(upper.startswith(prefix) for prefix in _BENCHMARK_PREFIXES):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{upper} parece un indice de referencia, no una tesis. "
                    "El indice se usa solo como benchmark del alpha."
                ),
            )


def _load_run(db: Session, run_id: int):
    from app.models.thesis_backtest import BacktestRun

    run = db.get(BacktestRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Backtest no encontrado")
    return run


@router.post("", status_code=202)
def launch_backtest(payload: BacktestRequest, db: Session = Depends(get_db)) -> dict:
    """Encola una rejilla ticker x fecha y devuelve el estado honesto del job.

    Idempotente: reenviar los mismos parámetros devuelve la ejecución existente
    en vez de recomputar. Un backtest es determinista y caro; volver a pedirlo es
    un replay, no trabajo nuevo.
    """
    if payload.start > payload.end:
        raise HTTPException(status_code=400, detail="start es posterior a end")
    _reject_benchmarks(payload.tickers)
    try:
        grid = build_grid(payload.start, payload.end, payload.step)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not grid:
        raise HTTPException(
            status_code=400, detail="La rejilla esta vacia: no hay ningun corte en el rango"
        )
    total = len(grid) * len(payload.tickers)
    if total > MAX_CELLS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{total} celdas superan el maximo de {MAX_CELLS}. "
                "Reduce el rango, el paso o el numero de tickers."
            ),
        )

    run, created = enqueue_backtest(
        db,
        tickers=payload.tickers,
        start=payload.start,
        end=payload.end,
        step=payload.step,
        as_of_strategy=payload.as_of_strategy,
        thesis_filter=payload.thesis_filter,
        request_id=payload.request_id,
    )
    body = run_payload(run)
    body["created"] = created
    body["celdas_planificadas"] = total
    body["cortes"] = [day.isoformat() for day in grid]
    body["nota"] = (
        "Fase asincrona: consulta el estado y el informe con GET /{run_id} y "
        "GET /{run_id}/report cuando termine. Sin ETA estimada."
    )
    return body


@router.get("/{run_id}")
def backtest_status(run_id: int, db: Session = Depends(get_db)) -> dict:
    """Estado del backtest: celdas hechas, rechazos de look-ahead y degradadas."""

    run = _load_run(db, run_id)
    from sqlalchemy import func, select

    from app.models.thesis_backtest import BacktestCellRow

    rows = db.execute(
        select(BacktestCellRow.status, func.count())
        .where(BacktestCellRow.run_id == run_id)
        .group_by(BacktestCellRow.status)
    ).all()
    by_status = {status: count for status, count in rows}
    return {
        "run_id": run.id,
        "workflow_name": WORKFLOW_NAME,
        "estado": run.status,
        "tickers": list(run.tickers or []),
        "rango": {"start": run.start.isoformat(), "end": run.end.isoformat()},
        "step": run.step,
        "as_of_strategy": run.as_of_strategy,
        "parametros": run.params,
        "celdas": {
            "planificadas": run.cells_total,
            "hechas": run.cells_done,
            "por_estado": by_status,
        },
        "error": run.error,
        "creado": run.created_at.isoformat() if run.created_at else None,
        "terminado": run.finished_at.isoformat() if run.finished_at else None,
    }


@router.get("/{run_id}/report")
def backtest_report(run_id: int, db: Session = Depends(get_db)) -> dict:
    """El informe: hit-rate, retornos, alpha, cobertura y advertencias.

    Incluye siempre el numero de celdas y la dispersion junto a cualquier
    hit-rate. Un 100% sobre cuatro celdas no es un resultado, y publicarlo sin
    el denominador es como un backtest acaba citado como prueba de alfa.
    """
    _load_run(db, run_id)
    try:
        return ThesisBacktestService().report(db, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{run_id}/cells")
def backtest_cells(
    run_id: int,
    ticker: str | None = Query(default=None),
    as_of: date | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=MAX_PAGE),
    db: Session = Depends(get_db),
) -> dict:
    """Celdas de la rejilla, con su ``as_of`` y su ``evidence_cutoff`` al lado.

    Los filtros son opcionales pero recommended: sin ellos la respuesta es la
    primera pagina de la rejilla, no el estado de un ticker.
    """
    _load_run(db, run_id)
    rows = ThesisBacktestService().cells(db, run_id, ticker=ticker, as_of=as_of)
    page = rows[:limit]
    return {
        "run_id": run_id,
        "total": len(rows),
        "devueltas": len(page),
        "limit": limit,
        "filtros": {"ticker": ticker, "as_of": as_of.isoformat() if as_of else None},
        "celdas": [_cell_payload(row) for row in page],
    }


def _cell_payload(row) -> dict:
    """Serialise a cell. Numbers stay ``None``; nothing is ever back-filled.

    ``precio_actual`` and ``fair_value`` are separate fields on purpose: the
    current price is a fact about that day, the fair value is an opinion built
    from the evidence available that day. A cell that abstained has the first
    and not the second, and this payload must never blur that.
    """
    return {
        "ticker": row.ticker,
        "as_of": row.as_of.isoformat(),
        "evidence_cutoff": row.evidence_cutoff.isoformat(),
        "estado": row.status,
        "motor": row.engine_key,
        "model_version": row.model_version,
        "fair_value": float(row.fair_value) if row.fair_value is not None else None,
        "escenarios": {
            "bear": float(row.bear_value) if row.bear_value is not None else None,
            "base": float(row.base_value) if row.base_value is not None else None,
            "bull": float(row.bull_value) if row.bull_value is not None else None,
        },
        "precio_actual": float(row.current_price) if row.current_price is not None else None,
        "precio_fecha": row.price_date.isoformat() if row.price_date else None,
        "precio_fuente": row.price_source,
        "upside": float(row.upside) if row.upside is not None else None,
        "claims": {
            "total": row.n_claims,
            "con_evidencia": row.n_claims_with_evidence,
            "source_coverage_score": row.source_coverage_score,
        },
        "debate_verdict": row.debate_verdict,
        "degradada": row.degraded,
        "degradada_motivo": row.degraded_reason,
        "lookahead_violations": list(row.lookahead_violations or []),
        "excluded_future_inputs": list(row.excluded_future_inputs or []),
        "unverifiable_inputs": list(row.unverifiable_inputs or []),
        "missing_inputs": list(row.missing_inputs or []),
        "publication_blockers": list(row.publication_blockers or []),
        "point_in_time": row.point_in_time or {},
        "retornos_realizados": row.realized or {},
        "cell_hash": row.cell_hash,
        "nota": (
            None
            if row.fair_value is not None
            else f"{ND}: celda sin fair value (estado={row.status})"
        ),
    }
