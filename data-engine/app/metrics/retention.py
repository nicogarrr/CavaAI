"""Poda de retencion de las metricas (#E5).

Una tabla de metricas sin poda es una bomba de relojería en Postgres: crece sin
limite, y el indice de ``api_latency_windows`` termina siendo lo mas grande de la
base mientras el indice lo consulta un endpoint al dia. La retencion esta
DECLARADA en `app/metrics/config.RETENTION_DAYS` y la poda se ejecuta desde la
misma tarea programada que calcula las metricas, con los mismos indices que las
lecturas.

Que se poda y por que:

- ``api_latency_windows`` en minuto: 7 dias. Es la granularidad de un incidente;
  pasado un semana, nadie abre un grafico de minutos de hace un mes.
- ``api_latency_windows`` en hora: 60 dias. Es la ventana que se consulta.
- ``api_latency_windows`` en dia: 400 dias. Cuatro anos de comparativa de SLO.
- ``queue_depth_snapshots``: 14 dias. 6 colas x 24 h x 14 d son ~2.000 filas.
- ``thesis_hit_rate_cells`` y ``evidence_coverage_snapshots``: 800 dias. Un
  snapshot por tenant y dia; 800 dias son casi dos anos de track record.

La poda es un DELETE acotado por fecha, nunca un TRUNCATE: si el reloj va
equivocado, un TRUNCATE se lleva el historico entero.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.metrics import config
from app.models.metrics import (
    ApiLatencyWindow,
    EvidenceCoverageSnapshot,
    QueueDepthSnapshot,
    ThesisHitRateCell,
)

logger = logging.getLogger(__name__)

# Orden de la poda: de la mas voluminosa a la mas pequena, para que un corte de
# luz a mitad no deje sin podar la tabla grande.
PRUNE_ORDER = (
    ("api_latency_windows:minute", ApiLatencyWindow, "window_start"),
    ("api_latency_windows:hour", ApiLatencyWindow, "window_start"),
    ("api_latency_windows:day", ApiLatencyWindow, "window_start"),
    ("queue_depth_snapshots", QueueDepthSnapshot, "observed_at"),
    ("thesis_hit_rate_cells", ThesisHitRateCell, "as_of"),
    ("evidence_coverage_snapshots", EvidenceCoverageSnapshot, "as_of"),
)


def cutoff_for(key: str, now: datetime) -> datetime:
    return now - timedelta(days=config.retention_days(*key.split(":")))


def prune_expired(
    db: Session,
    *,
    now: datetime | None = None,
    tables: tuple[str, ...] | None = None,
    dry_run: bool = False,
) -> dict:
    """Borra lo que exceda la retencion declarada. Idempotente.

    `dry_run` cuenta sin borrar: sirve para responder "cuanto ocupa esto" sin
    tocar la base de produccion desde un endpoint.
    """
    from app.metrics.latency import utcnow_naive

    moment = now or utcnow_naive()
    report: dict[str, dict] = {}
    for key, model, column in PRUNE_ORDER:
        if tables is not None and model.__tablename__ not in tables and key not in tables:
            continue
        cutoff = cutoff_for(key, moment)
        field = getattr(model, column)
        # La ventana (minute/hour/day) solo existe en api_latency_windows; las
        # demas tablas tienen una sola politica por tabla.
        window_size = key.split(":", 1)[1] if ":" in key else None
        if window_size and model is ApiLatencyWindow:
            statement = delete(model).where(
                field < cutoff, ApiLatencyWindow.window_size == window_size
            )
            count_statement = select(func.count()).select_from(model).where(
                field < cutoff, ApiLatencyWindow.window_size == window_size
            )
        else:
            statement = delete(model).where(field < cutoff)
            count_statement = select(func.count()).select_from(model).where(field < cutoff)
        if dry_run:
            deleted = int(db.scalar(count_statement) or 0)
        else:
            deleted = int(db.execute(statement).rowcount or 0)
        report[key] = {
            "tabla": model.__tablename__,
            "retencion_dias": config.retention_days(*key.split(":")),
            "corte": cutoff.isoformat(),
            "filas": deleted,
            "modo": "conteo" if dry_run else "borrado",
        }
    if not dry_run:
        db.commit()
    else:
        db.rollback()
    return {"podado": report}


def retention_report() -> dict:
    """La politica de retencion, expuesta por la API para que sea auditable."""
    return {
        key: {
            "tabla": model.__tablename__,
            "retencion_dias": config.retention_days(*key.split(":")),
            "columna_corte": column,
            "ejecuta": "refresh_backend_metrics (tarea programada)",
        }
        for key, model, column in PRUNE_ORDER
    }