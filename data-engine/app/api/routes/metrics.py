"""API de metricas de backend: `GET /api/metrics/...` (#E5).

Cuatro endpoints, uno por pregunta, todos con **ventana** y **tenant**
explicitos en la respuesta y paginacion donde devuelven series:

- ``GET /api/metrics/latencia``      p50/p95/p99 por endpoint (precalculado).
- ``GET /api/metrics/cola``          profundidad y salud de workers.
- ``GET /api/metrics/hit-rate``      ¿acertaron las tesis? con denominador.
- ``GET /api/metrics/evidencia``     % de claims con evidencia + distribucion.
- ``GET /api/metrics/retencion``     politica de retencion declarada y que se
                                    podaria (con ``?dry_run=true`` no borra).
- ``GET /api/metrics/prometheus``    el mismo contenido en texto Prometheus.

Nada de esto calcula nada pesado: se limita a leer snapshots ya precalculados por
`app.metrics.precompute`. Un "POST /recalcular" encola la tarea; recalcular en el
request seria quemar la base de produccion.

**Tenant.** Todos los handlers leen `db.info["tenant_id"]`, que `get_db` inyecta a
partir de la identidad firmada, y las tablas de latencia / hit-rate / evidencia
son `TenantOwnedMixin`, asi que el aislamiento lo pone la sesion y no el handler.
El tenant se devuelve SIEMPRE en la respuesta (`"tenant": {"id": ...}`) para que
quien lee el JSON sepa de quien son los numeros y no tenga que suponerlo.

Integracion: este modulo NO se registra solo. El `include_router` va en
`app/api/router.py`, que esta congelado mientras otros agentes trabajan sobre el.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.metrics import config, latency, prometheus, stats
from app.metrics import evidence as evidence_stats
from app.metrics import queue as queue_stats
from app.metrics import retention as retention_stats
from app.metrics import thesis as thesis_stats

router = APIRouter()

DEFAULT_LIMIT = 50
MAX_LIMIT = 500


def _naive_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _tenant_block(db: Session) -> dict:
    tenant_id = db.info.get("tenant_id")
    return {
        "id": tenant_id,
        "origen": "identidad firmada de Research OS (db.info['tenant_id'])",
        "aislado_por": "TenantOwnedMixin + with_loader_criteria de la sesion",
    }


def _window(window_start: datetime, window_size: str) -> dict:
    return {
        "inicio": window_start.isoformat(),
        "tamano": window_size,
        "fin": stats.next_window_start(window_start, window_size).isoformat(),
    }


def _resolve_window(window_size: str, at: datetime | None) -> tuple[datetime, str]:
    size = window_size if window_size in config.WINDOW_SIZES else config.latency_window()
    return stats.window_start(at or _naive_now(), size), size


@router.get("/latencia")
def metricas_latencia(
    ventana: str = Query(default="", description="minute | hour | day"),
    momento: datetime | None = Query(default=None, description="Fin de la ventana"),
    limite: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    desplazamiento: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    """Latencia por endpoint: p50/p95/p99, errores y sobrecarga del middleware."""
    window_start, window_size = _resolve_window(ventana, momento)
    rows = latency.rows_for_window(db, window_start=window_start, window_size=window_size)
    by_route = latency.by_route(rows, limite, desplazamiento)
    return {
        "metrica": "latencia_por_endpoint",
        "tenant": _tenant_block(db),
        "ventana": _window(window_start, window_size),
        "total": latency.latency_summary(rows),
        "por_endpoint": by_route,
        "notas": [
            "las rutas se agrupan por PLANTILLA (`/api/research/{ticker}`), no por URL crudo",
            "los percentiles salen de un histograma de 18 cajones, no de la media",
            "el histograma guarda el tope del ultimo cajon, no el maximo exacto",
            "es un agregado por ventana: no hay un log por peticion",
        ],
        "retencion_dias": config.retention_days("api_latency_windows", window_size),
    }


@router.get("/cola")
def metricas_cola(
    ventana: str = Query(default="hour", description="hour | day"),
    db: Session = Depends(get_db),
) -> dict:
    """Estado de cada cola: encolado / en curso / fallido / reintentos y edad.

    Se lee del ultimo snapshot precalculado. Para ir a Redis ahora esta
    `/cola/sondar`, que va en su propio endpoint porque hace una ida a Redis y una
    escritura: mezclarla con la lectura convertiria un GET barato en uno caro.
    """
    window_size = ventana if ventana in config.WINDOW_SIZES else config.WINDOW_HOUR
    return _cola_payload(db, window_size)


def _cola_payload(db: Session, window_size: str) -> dict:
    rows = queue_stats.latest_snapshots(db, window_size=window_size)
    incidentes = [
        queue_stats.queue_payload(row) for row in rows if row.status == queue_stats.STALL_STATUS
    ]
    return {
        "metrica": "profundidad_de_cola",
        "tenant": _tenant_block(db),
        "ambito": "plataforma",
        "ambito_nota": (
            "las colas de Dramatiq son infraestructura compartida entre tenants: la tabla "
            "no lleva tenant_id y el dato no es de un usuario. No es una excepcion de "
            "aislamiento, es que la dimension no existe."
        ),
        "ventana": {
            "inicio": stats.window_start(_naive_now(), window_size).isoformat(),
            "tamano": window_size,
        },
        "colas": [queue_stats.queue_payload(row) for row in rows],
        "incidentes": incidentes,
        "incidentes_total": len(incidentes),
        "criterio_incidente": (
            f"trabajo encolado mas viejo de {config.queue_stall_seconds():.0f} s con 0 "
            "mensajes en curso: eso es un worker parado, no una cola profunda"
        ),
        "retencion_dias": config.retention_days("queue_depth_snapshots"),
    }


@router.post("/cola/sondar")
def metricas_cola_sondar(db: Session = Depends(get_db)) -> dict:
    """Sondea Redis AHORA y persiste el snapshot. Diagnostico, no monitorizacion.

    Vive en su propio endpoint y no en `?sondar=` porque hace una ida a Redis y
    una escritura: mezclarla con la lectura convertiria un GET barato en uno caro.
    """
    states = queue_stats.probe_all()
    queue_stats.persist_states(db, states, window_size=config.WINDOW_HOUR)
    return {
        "metrica": "profundidad_de_cola",
        "accion": "sonda manual",
        "colas": [state.as_dict() for state in states],
        "incidentes_total": sum(
            1 for state in states if state.status == queue_stats.STALL_STATUS
        ),
    }


@router.get("/hit-rate")
def metricas_hit_rate(
    horizonte: int | None = Query(default=None, description="Filtra un horizonte en dias"),
    as_of: date | None = Query(default=None, description="Dia de calculo (por defecto, hoy)"),
    limite: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    desplazamiento: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    """Hit-rate de tesis por horizonte, decision, sector y calidad de evidencia.

    Cada celda trae numerador, denominador y TODOS los excluidos. Una celda sin
    evaluados devuelve N/D con el desglose de exclusiones, no 0.
    """
    today = as_of or _naive_now().date()
    rows, total = thesis_stats.cells_for(
        db, as_of=today, horizon=horizonte, limit=limite, offset=desplazamiento
    )
    return {
        "metrica": "hit_rate_de_tesis",
        "tenant": _tenant_block(db),
        "as_of": today.isoformat(),
        "precalculado": True,
        "total_celdas": total,
        "limite": limite,
        "desplazamiento": desplazamiento,
        "celdas": [thesis_stats.hit_rate_payload(row) for row in rows],
        "definiciones": (rows[0].definitions if rows else None)
        or thesis_stats.hit_rate_definitions(
            today, config.hit_rate_horizons(), _benchmark_present(db)
        ),
        "notas": [
            "el denominador es `hits + misses`; las celdas sin evaluados devuelven N/D",
            "la dimension `calidad_evidencia` usa ThesisVersion.source_coverage_score",
            "el alpha usa ^GSPC entre las MISMAS fechas; sin serie, N/D con motivo",
            "esta todo precalculado: recalcular por request quemaria la base",
        ],
        "retencion_dias": config.retention_days("thesis_hit_rate_cells"),
    }


def _benchmark_present(db: Session) -> int | None:
    return thesis_stats.benchmark_company_id(db)


@router.get("/evidencia")
def metricas_evidencia(
    as_of: date | None = Query(default=None, description="Dia del snapshot"),
    db: Session = Depends(get_db),
) -> dict:
    """% de claims con evidencia, con distribucion y breakdown del SourceAuditor."""
    today = as_of or _naive_now().date()
    snapshot = evidence_stats.latest_snapshot(db, as_of=today)
    if snapshot is None:
        return {
            "metrica": "claims_con_evidencia",
            "tenant": _tenant_block(db),
            "as_of": today.isoformat(),
            "materiales_con_evidencia": stats.indisponible(
                "no hay ningun snapshot precalculado para este tenant; ejecuta "
                "la tarea refresh_backend_metrics"
            ),
            "distribucion_por_tesis": stats.indisponible("sin snapshot"),
            "source_auditor": stats.indisponible("sin snapshot"),
            "retencion_dias": config.retention_days("evidence_coverage_snapshots"),
        }
    return {
        "metrica": "claims_con_evidencia",
        "tenant": _tenant_block(db),
        "precalculado": True,
        **evidence_stats.evidence_payload(snapshot),
        "por_sector": evidence_stats.sector_breakdown(db),
        "retencion_dias": config.retention_days("evidence_coverage_snapshots"),
    }


@router.get("/retencion")
def metricas_retencion(
    solo_lectura: bool = Query(default=True, description="Cuenta sin borrar"),
    db: Session = Depends(get_db),
) -> dict:
    """Politica de retencion DECLARADA y que se podaria con ella.

    Con `?solo_lectura=false` borra de verdad, asi que el default es no borrar.
    """
    return {
        "metrica": "retencion_de_metricas",
        "tenant": _tenant_block(db),
        "politica": retention_stats.retention_report(),
        "podado": retention_stats.prune_expired(db, dry_run=solo_lectura),
        "modo": "conteo" if solo_lectura else "borrado",
    }


@router.get("/prometheus", response_class=PlainTextResponse)
def metricas_prometheus(
    db: Session = Depends(get_db),
) -> PlainTextResponse:
    """El mismo contenido en texto Prometheus (contrato estandar, sin dependencias)."""
    window_start, window_size = _resolve_window(config.latency_window(), None)
    today = _naive_now().date()
    rows, _total = thesis_stats.cells_for(db, as_of=today, limit=MAX_LIMIT)
    body = prometheus.render(
        latency=latency.rows_for_window(db, window_start=window_start, window_size=window_size),
        queues=queue_stats.latest_snapshots(db, window_size=config.WINDOW_HOUR),
        hit_rates=rows,
        evidence=evidence_stats.latest_snapshot(db, as_of=today),
        tenant_id=db.info.get("tenant_id"),
    )
    return PlainTextResponse(content=body, media_type=prometheus.CONTENT_TYPE)


@router.post("/recalcular", status_code=202)
def metricas_recalcular(db: Session = Depends(get_db)) -> dict:
    """Encola la tarea programada. NO calcula aqui.

    Recalcular en el request es como se quema una base de produccion: el hit-rate
    une precios, tesis y benchmark. Esto encola y responde 202.
    """
    from app.metrics.precompute import actor

    tenant_id = db.info.get("tenant_id")
    user_id = db.info.get("user_id")
    if actor is None:
        return stats.indisponible(
            "el actor de Dramatiq no esta disponible en este proceso"
        )
    if tenant_id is None or not user_id:
        return stats.indisponible("la peticion no lleva identidad de tenant")
    message = actor.send(tenant_id, user_id)
    return {
        "estado": "encolado",
        "actor": actor.actor_name,
        "broker_message_id": str(message.message_id),
        "nota": "el calculo ocurre en la tarea programada, no en este request",
    }


@router.get("/resumen")
def metricas_resumen(db: Session = Depends(get_db)) -> dict:
    """Las cuatro metricas en una llamada. Todo precalculado, todo con su N/D."""
    window_start, window_size = _resolve_window(config.latency_window(), None)
    today = _naive_now().date()
    cells, _total = thesis_stats.cells_for(db, as_of=today, limit=MAX_LIMIT)
    global_cells = [
        cell for cell in cells
        if cell.decision == thesis_stats.ANY and cell.sector == thesis_stats.ANY
        and cell.evidence_bucket == thesis_stats.ANY
    ]
    snapshot = evidence_stats.latest_snapshot(db, as_of=today)
    return {
        "metrica": "resumen_de_metricas_de_backend",
        "tenant": _tenant_block(db),
        "ventana": _window(window_start, window_size),
        "as_of": today.isoformat(),
        "latencia": latency.latency_summary(
            latency.rows_for_window(db, window_start=window_start, window_size=window_size)
        ),
        "cola": {
            "colas": len(queue_stats.latest_snapshots(db, window_size=config.WINDOW_HOUR)),
            "incidentes": sum(
                1 for row in queue_stats.latest_snapshots(db, window_size=config.WINDOW_HOUR)
                if row.status == queue_stats.STALL_STATUS
            ),
        },
        "hit_rate": [thesis_stats.hit_rate_payload(cell) for cell in global_cells],
        "evidencia": evidence_stats.evidence_payload(snapshot) if snapshot else
        stats.indisponible("sin snapshot de evidencia precalculado"),
    }


@router.get("/ventanas")
def metricas_ventanas(db: Session = Depends(get_db)) -> dict:
    """Ventanas disponibles y hasta donde llegan los datos. Para pintar un selector."""
    today = _naive_now().date()
    return {
        "metrica": "ventanas_disponibles",
        "tenant": _tenant_block(db),
        "ventanas_tamano": list(config.WINDOW_SIZES),
        "ventana_latencia_por_defecto": config.latency_window(),
        "horizontes_dias": list(config.hit_rate_horizons()),
        "materialidad_minima": config.materiality_threshold(),
        "as_of_hoy": today.isoformat(),
        "desde": (today - timedelta(days=config.retention_days("thesis_hit_rate_cells"))).isoformat(),
        "retencion": retention_stats.retention_report(),
    }