"""Precalculo programado de las metricas (#E5).

**Por que esto es una tarea y no un endpoint.** El hit-rate une precios, tesis y
benchmark; la cobertura de evidencia agrega claims, evidencias, auditorias y
tesis; la poda borra. Recalcular eso en cada peticion es exactamente como se
quema una base de produccion. Los endpoints LEEN estos snapshots precalculados y,
como mucho, ofrecen un "recalcular ahora" explicito.

El actor va a la cola `default`, que es la que ya consumen los workers del
compose: asi no hace falta anadir `-Q metrics` ni tocar el compose (fichero
compartido y congelado).

`WORKERS_ENABLED`: este modulo no lee ni escribe ese flag. El actor solo se
encola desde el scheduler, que main.py ya no arranca cuando el flag es false, de
modo que los tests siguen sin generar metricas.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.metrics import config
from app.metrics import evidence as evidence_stats
from app.metrics import queue as queue_stats
from app.metrics import retention as retention_stats
from app.metrics import thesis as thesis_stats

logger = logging.getLogger(__name__)

ACTOR_NAME = "refresh_backend_metrics"


def tenant_session(tenant_id: int | None, user_id: str | None) -> Session:
    """Sesion con contexto de tenant, con el mismo criterio que los actores."""
    from app.models import Tenant

    db = SessionLocal()
    if tenant_id is None or not user_id:
        db.close()
        raise ValueError("tenant_id and user_id are required for background jobs")
    tenant = db.get(Tenant, tenant_id)
    if tenant is None or tenant.status != "active":
        db.close()
        raise ValueError(f"Active tenant {tenant_id} was not found")
    db.info["tenant_id"] = tenant.id
    db.info["user_id"] = user_id
    return db


def compute_backend_metrics(
    tenant_id: int | None = None,
    user_id: str | None = None,
    *,
    include_queue: bool = True,
    prune: bool = True,
    dry_run_prune: bool = False,
) -> dict[str, Any]:
    """Recalcula hit-rate, cobertura y cola del tenant, y poda lo caducado.

    Idempotente: recalcular replaces las celdas del dia en vez de apilarlas, y la
    poda es un DELETE acotado por fecha. Se puede llamar a mano sin miedo.
    """
    started = datetime.now(UTC).replace(tzinfo=None)
    today: date = started.date()
    result: dict[str, Any] = {"as_of": today.isoformat(), "tenant_id": tenant_id}

    db = tenant_session(tenant_id, user_id)
    try:
        cells, outcomes, _definitions = thesis_stats.compute_hit_rate(db, as_of=today)
        result["hit_rate"] = {
            "celdas": len(cells),
            "tesis_evaluadas": len({o.thesis_version_id for o in outcomes}),
            "horizontes": list(config.hit_rate_horizons()),
        }
        snapshot = evidence_stats.compute_evidence_coverage(db, as_of=today)
        result["evidencia"] = {
            "claims_totales": snapshot.claims_total,
            "materiales": snapshot.material_claims,
            "materiales_con_evidencia": snapshot.material_with_evidence,
            "materiales_oficiales": snapshot.material_with_official,
            "p10_cobertura": snapshot.coverage_p10,
            "p50_cobertura": snapshot.coverage_p50,
            "p90_cobertura": snapshot.coverage_p90,
        }
        result["evidencia_por_sector"] = evidence_stats.sector_breakdown(db)
    finally:
        db.rollback()
        db.close()

    if include_queue:
        states = queue_stats.probe_all()
        db = tenant_session(tenant_id, user_id)
        try:
            snapshots = queue_stats.persist_states(db, states, now=started)
            incidentes = [
                {"cola": row.queue_name, "motivo": row.incident_reason}
                for row in snapshots
                if row.status == queue_stats.STALL_STATUS
            ]
            result["cola"] = {
                "colas": len(snapshots),
                "incidentes_total": len(incidentes),
                "incidentes": incidentes,
            }
        finally:
            db.rollback()
            db.close()

    if prune:
        db = tenant_session(tenant_id, user_id)
        try:
            result["retencion"] = retention_stats.prune_expired(
                db, now=started, dry_run=dry_run_prune
            )
        finally:
            db.rollback()
            db.close()

    finished = datetime.now(UTC).replace(tzinfo=None)
    result["duracion_s"] = round((finished - started).total_seconds(), 3)
    return result


def _register_actor():
    """Declara el actor en Dramatiq. Import perezroso: dramatiq es opcional.

    El decorador `@dramatiq.actor` llama a `dramatiq.get_broker()`, que falla si
    nadie ha fijado un broker todavia. Por eso se importa `dramatiq_app` ANTES de
    declarar el actor: ese modulo es quien hace `dramatiq.set_broker(broker)`.

    El decorador ya registra el actor en el broker (`declare_actor`), asi que
    aqui no se emite ningun evento a mano: emitirlo otra vez lo declararia dos
    veces.
    """
    try:
        import dramatiq

        from app.workers import dramatiq_app  # noqa: F401 — fija el broker global
    except Exception as exc:  # noqa: BLE001 — sin dramatiq no hay actor y punto
        logger.debug("actor de metricas no registrado: %s", type(exc).__name__)
        return None

    @dramatiq.actor(actor_name=ACTOR_NAME, max_retries=2)
    def refresh_backend_metrics(tenant_id: int | None, user_id: str | None) -> dict[str, Any]:
        try:
            return compute_backend_metrics(tenant_id, user_id)
        except Exception as exc:  # noqa: BLE001 — un job de metricas no tumba el worker
            return {
                "status": "error",
                "error": {"type": type(exc).__name__},
                "hint": "la tarea de metricas fallo; el resto del worker sigue vivo",
            }

    return refresh_backend_metrics


class _ActorUnavailable:
    """En el proceso donde no hay Dramatiq (imports de solo lectura, tests).

    Existe para que `from app.metrics.precompute import refresh_backend_metrics`
    nunca falle: `app/workers/scheduler.py` lo importa a nivel de modulo y
    `app/api/routes/health.py` construye el scheduler en cada sonda, asi que una
    ImportError aqui se convertiria en un /api/health 500.
    """

    actor_name = ACTOR_NAME

    def send(self, *_args: object, **_kwargs: object):
        raise RuntimeError("Dramatiq no esta disponible en este proceso")


refresh_backend_metrics = _register_actor() or _ActorUnavailable()
actor = refresh_backend_metrics