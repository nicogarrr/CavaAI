"""Modelos de las metricas de backend (#E5).

Vivien en su propio modulo, y no en `app/models/entities.py`, porque ese
fichero esta congelado mientras otros 17 agentes trabajan sobre el. Se registran
en `Base.metadata` via el import que hace `app/models/__init__.py`, asi que
`Base.metadata.create_all()` (lo que usan los tests) las crea igual que el resto.

Cuatro tablas, cuatro preguntas:

- ``api_latency_windows``: agregado por ventana con histograma de duraciones.
  NO es un log por request: una fila por (ventana, ruta, metodo, codigo), con
  contadores y un histograma de 18 cajones. Un log por request en la misma BD
  que el negocio es contention, crecimiento sin poda y un vector de fuga de
  datos de usuario.
- ``queue_depth_snapshots``: estado de cada cola Dramatiq. Es infraestructura de
  plataforma, NO dato de tenant (las colas de Dramatiq no se particionan), asi
  que no lleva ``tenant_id``; el API lo declara explicitamente en vez de
  fingir un particionado que no existe.
- ``thesis_hit_rate_cells``: una celda por (fecha, horizonte, decision, sector,
  calidad de evidencia) con numerator, denominador y TODOS los excluidos.
- ``evidence_coverage_snapshots``: % de claims con evidencia con DISTRIBUCION
  (p10/p50/p90 + histograma), no solo la media.

Retencion declarada en ``app/metrics/config.RETENTION_DAYS`` y aplicada por
``app/metrics/retention.prune_expired``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

# Alias del tipo `date` (mismo truco que en entities.py): dentro del cuerpo de
# una clase, `date: Mapped[date]` hace que el anotado se refiera a la propia
# columna mientras se evalua y pyright lo rechaza.
_DateT = date

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.entities import TenantOwnedMixin


def utcnow() -> datetime:
    """UTC *naive*, a proposito.

    Los timestamps de estas tablas son `timestamp without time zone` y todos se
    escriben en UTC. La alternativa (timestamptz) hace que la misma fila se lea
    como naive en SQLite y como aware en Postgres segun el dialecto, y que un
    `WHERE window_start == <aware>` no encuentre nada en los tests de SQLite:
    dos backends, dos veridades para la misma pregunta. Fijando la zona aqui la
    fila significa lo mismo en los dos, y las comparaciones son exactas.
    """
    return datetime.now(UTC).replace(tzinfo=None)

# Bordes superiores del histograma de duraciones, en milisegundos. 18 cajones:
# desde 1 ms (una ruta de cache) hasta 300 s (una ingesta de 3 h que se
# colorea aqui, aunque el valor real este por encima). El borde superior del
# ultimo cajon finito se usa como techo declarado del percentil, no como
# estimacion inventada.
LATENCY_BUCKET_EDGES: tuple[float, ...] = (
    1.0, 2.0, 5.0, 10.0, 25.0, 50.0, 100.0, 250.0, 500.0,
    1000.0, 2500.0, 5000.0, 10000.0, 30000.0, 60000.0, 120000.0, 300000.0,
)
LATENCY_BUCKET_COLUMNS: tuple[str, ...] = (
    "le_1", "le_2", "le_5", "le_10", "le_25", "le_50", "le_100", "le_250", "le_500",
    "le_1000", "le_2500", "le_5000", "le_10000", "le_30000", "le_60000",
    "le_120000", "le_300000",
)
assert len(LATENCY_BUCKET_COLUMNS) == len(LATENCY_BUCKET_EDGES)


class ApiLatencyWindow(TenantOwnedMixin, Base):
    """Latencia agregada por ventana, con histograma. Un log por request no."""

    __tablename__ = "api_latency_windows"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "window_start",
            "window_size",
            "route_template",
            "method",
            "status_code",
            name="uq_api_latency_window",
        ),
        Index("ix_api_latency_windows_tenant_window", "tenant_id", "window_start"),
        Index("ix_api_latency_windows_route", "route_template", "window_start"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=False), index=True)
    window_size: Mapped[str] = mapped_column(String(10), default="hour")
    # Plantilla de ruta (`/api/research/{ticker}`), jamas la URL cruda: ni ids
    # ni tickers reales, para que la cardinalidad no crezca con el trafico.
    route_template: Mapped[str] = mapped_column(String(200), default="")
    method: Mapped[str] = mapped_column(String(10), default="GET")
    status_code: Mapped[int] = mapped_column(Integer, default=0)
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    duration_sum_ms: Mapped[float] = mapped_column(Float, default=0.0)
    # Sobrecarga del propio middleware, medida en el mismo request. Se reporta
    # con el middleware puesto y sin el: un instrumentador que no declara lo que
    # cuesta no es un instrumentador.
    overhead_samples: Mapped[int] = mapped_column(Integer, default=0)
    overhead_sum_ms: Mapped[float] = mapped_column(Float, default=0.0)
    overhead_max_ms: Mapped[float] = mapped_column(Float, default=0.0)
    le_1: Mapped[int] = mapped_column(Integer, default=0)
    le_2: Mapped[int] = mapped_column(Integer, default=0)
    le_5: Mapped[int] = mapped_column(Integer, default=0)
    le_10: Mapped[int] = mapped_column(Integer, default=0)
    le_25: Mapped[int] = mapped_column(Integer, default=0)
    le_50: Mapped[int] = mapped_column(Integer, default=0)
    le_100: Mapped[int] = mapped_column(Integer, default=0)
    le_250: Mapped[int] = mapped_column(Integer, default=0)
    le_500: Mapped[int] = mapped_column(Integer, default=0)
    le_1000: Mapped[int] = mapped_column(Integer, default=0)
    le_2500: Mapped[int] = mapped_column(Integer, default=0)
    le_5000: Mapped[int] = mapped_column(Integer, default=0)
    le_10000: Mapped[int] = mapped_column(Integer, default=0)
    le_30000: Mapped[int] = mapped_column(Integer, default=0)
    le_60000: Mapped[int] = mapped_column(Integer, default=0)
    le_120000: Mapped[int] = mapped_column(Integer, default=0)
    le_300000: Mapped[int] = mapped_column(Integer, default=0)
    # Todo lo que pasa de 300 s. Sin este contador el total de los cajones no
    # cerraria con el numero de peticiones y el p99 mentiria.
    overflow: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), default=utcnow, onupdate=utcnow
    )


class QueueDepthSnapshot(Base):
    """Estado de una cola Dramatiq en un instante. Plataforma, no de tenant."""

    __tablename__ = "queue_depth_snapshots"
    __table_args__ = (
        Index("ix_queue_depth_snapshots_queue_time", "queue_name", "observed_at"),
        Index("ix_queue_depth_snapshots_window", "window_start", "window_size"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    queue_name: Mapped[str] = mapped_column(String(80), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=utcnow, index=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=False), index=True)
    window_size: Mapped[str] = mapped_column(String(10), default="hour")
    # Encolado = en la lista, esperando a que un worker lo coja.
    #
    # `pending`, `delayed`, `in_flight` y `dead_lettered` son NULLABLE y SIN
    # default a proposito: `None` significa "no se pudo medir" (Redis caido) y
    # tiene que SOBREVIVIR al round-trip. Con un `default=0` en la columna,
    # SQLAlchemy aplica el default cuando el atributo vale None y el N/D se
    # convertiria en un 0 mentiroso en la base.
    pending: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delayed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # En curso = en el hash `.msgs` pero ya no en la lista: lo ha sacado un
    # worker y todavia no ha hecho ack.
    in_flight: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Fallidos = carta muerta (`.XQ`): se agotaron los reintentos.
    dead_lettered: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Edad del trabajo mas viejo encolado. La metrica que de verdad avisa de un
    # worker muerto: la profundidad sola no (una cola profunda con trabajo en
    # curso es backpressure, no una averia).
    oldest_age_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    oldest_age_exhaustive: Mapped[bool] = mapped_column(Boolean, default=False)
    oldest_age_sample: Mapped[int] = mapped_column(Integer, default=0)
    workers_live: Mapped[int | None] = mapped_column(Integer, nullable=True)
    workers_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    newest_heartbeat_age_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Contadores EN PROCESO (middleware Dramatiq). Solo tienen sentido si el
    # worker tiene instalado `install_queue_middleware()`; si no, None = N/D y
    # nunca 0, porque 0 seria "no se fallo nunca".
    processed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    skipped: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retried: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # ok | degradado | incidente. Nunca un numero: un worker parado no es un
    # statistic, es un incidente, y se reporta como tal con su razon.
    status: Mapped[str] = mapped_column(String(20), default="desconocido")
    incident_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(String(40), default="redis")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=utcnow)


class ThesisHitRateCell(TenantOwnedMixin, Base):
    """Hit-rate por celda, con numerador, denominador y excluidos visibles.

    Una celda es una combinacion de (horizonte, decision, sector, calidad de
    evidencia). `*` significa "agregado sobre esta dimension", de modo que la
    celda `(*,*,*,*)` es el total y las demas son los cortes. Un hit-rate sin
    `evaluated` y sin los `excluded_*` al lado es propaganda: es exactamente el
    fallo que la migracion 0046 ya sufrio en otro sitio (hit_rate 1.0 sobre 14
    celdas, con un aviso SOSPECHOSO).
    """

    __tablename__ = "thesis_hit_rate_cells"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "as_of",
            "horizon_days",
            "decision",
            "sector",
            "evidence_bucket",
            name="uq_thesis_hit_rate_cell",
        ),
        Index("ix_thesis_hit_rate_cells_tenant_as_of", "tenant_id", "as_of"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    as_of: Mapped[_DateT] = mapped_column(Date, index=True)  # noqa: F821  (alias del modulo)
    horizon_days: Mapped[int] = mapped_column(Integer, default=0)
    decision: Mapped[str] = mapped_column(String(40), default="*")
    sector: Mapped[str] = mapped_column(String(120), default="*")
    evidence_bucket: Mapped[str] = mapped_column(String(40), default="*")
    # Numerador y denominador, siempre. `evaluated` == hits + misses.
    hits: Mapped[int] = mapped_column(Integer, default=0)
    misses: Mapped[int] = mapped_column(Integer, default=0)
    evaluated: Mapped[int] = mapped_column(Integer, default=0)
    # Excluidos, uno por motivo. Son tan importantes como el numerador: sin
    # ellos no se sabe si el 80 % es del Que Se Evaluo o de lo que se pudo.
    excluded_neutral: Mapped[int] = mapped_column(Integer, default=0)
    excluded_rating_unknown: Mapped[int] = mapped_column(Integer, default=0)
    excluded_no_entry_price: Mapped[int] = mapped_column(Integer, default=0)
    excluded_no_exit_price: Mapped[int] = mapped_column(Integer, default=0)
    excluded_too_early: Mapped[int] = mapped_column(Integer, default=0)
    excluded_tie: Mapped[int] = mapped_column(Integer, default=0)
    excluded_no_benchmark: Mapped[int] = mapped_column(Integer, default=0)
    hit_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    median_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    p10_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    p90_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Alpha contra benchmark. `benchmark_status` != "ok" => alpha es None y
    # `benchmark_reason` dice por que (N/D con motivo, jamas 0 de relleno).
    benchmark_ticker: Mapped[str | None] = mapped_column(String(20), nullable=True)
    benchmark_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    alpha: Mapped[float | None] = mapped_column(Float, nullable=True)
    benchmark_status: Mapped[str] = mapped_column(String(20), default="N/D")
    benchmark_reason: Mapped[str | None] = mapped_column(String(160), nullable=True)
    # Snapshot de la regla determinista con la que se calculo esta celda. Sin
    # el, un hit-rate historico no es auditable.
    definitions: Mapped[dict | None] = mapped_column(JSON, default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), default=utcnow, onupdate=utcnow
    )


class EvidenceCoverageSnapshot(TenantOwnedMixin, Base):
    """% de claims con evidencia, con DISTRIBUCION y no solo la media.

    Si el 90 % de las tesis tiene 100 % y el 10 % tiene 0 %, la media de 90 % es
    una mentira. Por eso aqui se persisten p10/p50/p90 y el histograma de la
    cobertura por tesis, no solo el promedio.
    """

    __tablename__ = "evidence_coverage_snapshots"
    __table_args__ = (
        UniqueConstraint("tenant_id", "as_of", "scope", name="uq_evidence_coverage_snapshot"),
        Index("ix_evidence_coverage_tenant_as_of", "tenant_id", "as_of"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    as_of: Mapped[_DateT] = mapped_column(Date, index=True)  # noqa: F821  (alias del modulo)
    scope: Mapped[str] = mapped_column(String(40), default="global")
    claims_total: Mapped[int] = mapped_column(Integer, default=0)
    claims_with_evidence: Mapped[int] = mapped_column(Integer, default=0)
    material_claims: Mapped[int] = mapped_column(Integer, default=0)
    material_with_evidence: Mapped[int] = mapped_column(Integer, default=0)
    material_with_official: Mapped[int] = mapped_column(Integer, default=0)
    material_with_inferred: Mapped[int] = mapped_column(Integer, default=0)
    material_without_evidence: Mapped[int] = mapped_column(Integer, default=0)
    thesis_versions_considered: Mapped[int] = mapped_column(Integer, default=0)
    # Distribucion de la cobertura por tesis (0-100).
    coverage_p10: Mapped[float | None] = mapped_column(Float, nullable=True)
    coverage_p50: Mapped[float | None] = mapped_column(Float, nullable=True)
    coverage_p90: Mapped[float | None] = mapped_column(Float, nullable=True)
    coverage_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    coverage_histogram: Mapped[dict | None] = mapped_column(JSON, default=dict)
    # Distribucion de ThesisVersion.source_coverage_score (0-100), que es la
    # columna que ya persisten las tesis: no se inventa un campo nuevo.
    score_p10: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_p50: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_p90: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_histogram: Mapped[dict | None] = mapped_column(JSON, default=dict)
    # Breakdown del SourceAuditor. Son CONTADORES de las listas de claims, nunca
    # sus textos: un texto de claim es contenido de usuario y no va a una tabla
    # de agregados.
    audits_total: Mapped[int] = mapped_column(Integer, default=0)
    audits_passed: Mapped[int] = mapped_column(Integer, default=0)
    unsupported_total: Mapped[int] = mapped_column(Integer, default=0)
    weak_total: Mapped[int] = mapped_column(Integer, default=0)
    data_conflicts_total: Mapped[int] = mapped_column(Integer, default=0)
    required_fixes_total: Mapped[int] = mapped_column(Integer, default=0)
    auditor_mean_coverage: Mapped[float | None] = mapped_column(Float, nullable=True)
    materiality_threshold: Mapped[int] = mapped_column(Integer, default=7)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=utcnow)


__all__ = [
    "ApiLatencyWindow",
    "EvidenceCoverageSnapshot",
    "LATENCY_BUCKET_COLUMNS",
    "LATENCY_BUCKET_EDGES",
    "QueueDepthSnapshot",
    "ThesisHitRateCell",
    "utcnow",
]

