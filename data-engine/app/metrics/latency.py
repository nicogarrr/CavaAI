"""Latencia por endpoint: instrumentacion, agregado y lectura (#E5, metrica 1).

Decisiones, y por que:

**Middleware ASGI puro, no `BaseHTTPMiddleware`.** `BaseHTTPMiddleware` envuelve
cada request en una tarea y una stream de anyio; paga decenas de milisegundos en
algunos escenarios y aqui estariamos midiendo nuestro propio sobrecoste. Un
middleware ASGI que solo envuelve `send` paga dos llamadas por request.

**La plantilla sale del route, no de la URL.** `scope["route"].path` ya trae
`{ticker}`. Las otras dos defensas (cardinalidad acotada, sin query string, sin
PII) estan en `app/metrics/route_template.py`.

**Persistencia agregada, no un log por request.** Un dict en memoria por
(tenant, ventana, ruta, metodo, codigo) y un UPSERT por serie. Un INSERT por
request en la misma BD que el negocio es contention, crecimiento sin poda y un
vector de fuga de datos de usuario. Aqui la fila es un contador y un histograma:
cero PII por construccion.

**El volcado va en un hilo, no en el hilo del request.** El camino de la
peticion solo hace un `dict.get` y unas sumas; el UPSERT ocurre en un hilo daemon
que vuelca cada `BACKEND_METRICS_FLUSH_INTERVAL_S`. Si un request paga de vez en
cuando un UPSERT, el p95 que medimos incluye nuestro propio coste de escritura.

**p50/p95/p99, no la media.** La media mezcla el cache hit de 1 ms con la ingesta
de 3 s y no describe ninguna de las dos. El histograma de 18 cajones da
percentiles con la precision del ancho del cajon, que es la precision que un p99
merece.

**La sobrecarga se mide a si misma.** El middleware cronometra su propio trabajo
(el que no es la app downstream) y el recorder cronometra el suyo; ambos suman
en la misma columna `overhead_*`, con muestras y maximo. Un instrumentador que
no declara lo que cuesta no es un instrumentador.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.metrics import config, stats
from app.metrics.route_template import route_template
from app.models.metrics import (
    LATENCY_BUCKET_COLUMNS,
    LATENCY_BUCKET_EDGES,
    ApiLatencyWindow,
)

logger = logging.getLogger(__name__)

TENANT_STATE_KEY = "tenant_id"
OVERFLOW_ROUTE = "__overflow__"

PERCENTILE_METHOD = (
    "histograma de 18 cajones con interpolacion lineal dentro del cajon; "
    f"cola abierta por encima de {LATENCY_BUCKET_EDGES[-1]} ms"
)


def utcnow_naive() -> datetime:
    """UTC sin tzinfo. Los timestamps de metricas son naive por decision (#E5)."""
    return datetime.now(UTC).replace(tzinfo=None)


def bucket_index(duration_ms: float) -> int:
    """Indice del cajon; `len(EDGES)` significa "por encima del ultimo borde"."""
    for index, edge in enumerate(LATENCY_BUCKET_EDGES):
        if duration_ms <= edge:
            return index
    return len(LATENCY_BUCKET_EDGES)


@dataclass
class Observation:
    """Una medicion pendiente de agregarse a su ventana."""

    tenant_id: int | None
    window_start: datetime
    window_size: str
    route_template: str
    method: str
    status_code: int
    duration_ms: float
    error: bool
    overhead_ms: float = 0.0


@dataclass
class _Series:
    request_count: int = 0
    error_count: int = 0
    duration_sum_ms: float = 0.0
    overhead_samples: int = 0
    overhead_sum_ms: float = 0.0
    overhead_max_ms: float = 0.0
    buckets: list[int] = field(default_factory=lambda: [0] * (len(LATENCY_BUCKET_EDGES) + 1))


_SeriesKey = tuple[int | None, datetime, str, str, int]


class LatencyRecorder:
    """Buffer en memoria + UPSERT monotono. Un objeto por proceso.

    La escritura suma contadores, nunca asigna un valor absoluto: dos procesos
    que vuelcan a la vez sobre la misma fila se suman en vez de pisarse.
    """

    def __init__(
        self,
        *,
        window_size: str | None = None,
        max_route_series: int | None = None,
        flush_max_series: int | None = None,
        flush_interval_s: float | None = None,
    ) -> None:
        self._window_size = window_size or config.latency_window()
        self._max_route_series = max_route_series or config.max_route_series()
        self._flush_max_series = flush_max_series or config.flush_max_series()
        self._flush_interval_s = flush_interval_s or config.flush_interval_seconds()
        self._lock = threading.Lock()
        self._buffer: dict[_SeriesKey, _Series] = {}
        self._templates: dict[str, None] = {}
        self._last_flush = time.monotonic()
        self._dropped = 0
        self._overflowed = 0
        self._flusher: threading.Thread | None = None
        self._flusher_lock = threading.Lock()

    @property
    def window_size(self) -> str:
        return self._window_size

    @property
    def pending_series(self) -> int:
        with self._lock:
            return len(self._buffer)

    @property
    def dropped_observations(self) -> int:
        """Muestras perdidas por un fallo de escritura. Visible, no oculto."""
        with self._lock:
            return self._dropped

    @property
    def overflowed_observations(self) -> int:
        """Muestras colapsadas a `__overflow__` por el techo de cardinalidad."""
        with self._lock:
            return self._overflowed

    @property
    def tracked_templates(self) -> int:
        with self._lock:
            return len(self._templates)

    def normalize_route(self, scope: dict, fallback_path: str) -> str:
        """Plantilla de ruta con el techo de cardinalidad del recorder aplicado."""
        template = route_template(scope, fallback_path)
        if template == "__unmatched__":
            return template
        with self._lock:
            if template in self._templates:
                return template
            if len(self._templates) >= self._max_route_series:
                self._overflowed += 1
                return OVERFLOW_ROUTE
            self._templates[template] = None
            return template

    def record(self, observation: Observation) -> None:
        """Agrega una medicion al buffer. O(1) y sin I/O.

        El coste de este metodo se mide y se suma a la misma columna de
        sobrecarga que la del middleware: asi `overhead_*` es el coste total de
        instrumentar un request, no una estimacion de una de las dos mitades.
        """
        mark = time.perf_counter()
        key = (
            observation.tenant_id,
            observation.window_start,
            observation.route_template,
            observation.method,
            observation.status_code,
        )
        index = bucket_index(observation.duration_ms)
        with self._lock:
            series = self._buffer.get(key)
            if series is None:
                series = _Series()
                self._buffer[key] = series
            series.request_count += 1
            series.error_count += 1 if observation.error else 0
            series.duration_sum_ms += observation.duration_ms
            series.buckets[index] += 1
            due = len(self._buffer) >= self._flush_max_series or (
                time.monotonic() - self._last_flush >= self._flush_interval_s
            )
        own_ms = (time.perf_counter() - mark) * 1000.0
        with self._lock:
            series.overhead_samples += 1
            series.overhead_sum_ms += observation.overhead_ms + own_ms
            series.overhead_max_ms = max(
                series.overhead_max_ms, observation.overhead_ms + own_ms
            )
        if due:
            self.start_flusher()

    def drain(self) -> dict[_SeriesKey, _Series]:
        """Saca el buffer sin escribirlo (tests y precalculo)."""
        with self._lock:
            pending = self._buffer
            self._buffer = {}
            self._last_flush = time.monotonic()
            return pending

    def flush(self, db: Session | None = None) -> int:
        """Vuelca el buffer a la BD. Devuelve las series escritas.

        Nunca propaga el error: si la BD esta caida, el usuario ya tiene su
        respuesta y no la ensuciamos con un fallo de observabilidad. Las
        muestras perdidas se cuentan para que el hueco sea visible.
        """
        pending = self.drain()
        if not pending:
            return 0
        owned = db is None
        session = db
        if owned:
            from app.core.database import SessionLocal

            session = SessionLocal()
        try:
            write_series(session, self._window_size, pending)
        except Exception as exc:  # noqa: BLE001 — observabilidad nunca rompe
            with self._lock:
                self._dropped += sum(series.request_count for series in pending.values())
            logger.warning("volcado de latencia fallido: %s", type(exc).__name__, exc_info=True)
            return 0
        finally:
            if owned and session is not None:
                session.close()
        return len(pending)

    def start_flusher(self) -> threading.Thread | None:
        """Arranca (una sola vez) el hilo daemon que vuelca el buffer."""
        with self._flusher_lock:
            if self._flusher is not None and self._flusher.is_alive():
                return self._flusher
            thread = threading.Thread(
                target=self._flush_loop,
                name="cavaai-latency-flush",
                daemon=True,
            )
            self._flusher = thread
            thread.start()
            return thread

    def _flush_loop(self) -> None:
        while True:
            self.flush()
            time.sleep(self._flush_interval_s)


def _insert_factory(dialect: str):
    """`insert()` con UPSERT del dialecto, o None si no lo hay."""
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        return pg_insert
    if dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        return sqlite_insert
    return None


def _values_for(series: _Series) -> dict[str, Any]:
    values: dict[str, Any] = {
        "request_count": series.request_count,
        "error_count": series.error_count,
        "duration_sum_ms": series.duration_sum_ms,
        "overhead_samples": series.overhead_samples,
        "overhead_sum_ms": series.overhead_sum_ms,
        "overhead_max_ms": series.overhead_max_ms,
    }
    for name, count in zip(LATENCY_BUCKET_COLUMNS, series.buckets, strict=False):
        values[name] = count
    values["overflow"] = series.buckets[len(LATENCY_BUCKET_EDGES)]
    return values


def write_series(
    session: Session, window_size: str, pending: dict[_SeriesKey, _Series]
) -> None:
    """Suma cada serie a su fila.

    `tenant_id IS NULL` (trafico publico sin identidad: /api/health, /) no puede
    usar `ON CONFLICT`: en Postgres dos NULL no chocan en un indice unico y en
    SQLite el `ON CONFLICT` tampoco los iguala. Ese camino es lectura-escritura,
    que es correcto con la concurrencia baja de las rutas publicas. El camino
    con tenant usa UPSERT atomico, que es el que importa.
    """
    insert_factory = _insert_factory(session.get_bind().dialect.name)
    table = ApiLatencyWindow.__table__
    conflict_index = [
        table.c.tenant_id,
        table.c.window_start,
        table.c.window_size,
        table.c.route_template,
        table.c.method,
        table.c.status_code,
    ]
    for key, series in pending.items():
        tenant_id, window_start, template, method, status_code = key
        values = _values_for(series)
        if tenant_id is None or insert_factory is None:
            _merge_without_tenant(session, key, window_size, values)
            continue
        statement = insert_factory(ApiLatencyWindow).values(
            tenant_id=tenant_id,
            window_start=window_start,
            window_size=window_size,
            route_template=template,
            method=method,
            status_code=status_code,
            **values,
        )
        session.execute(
            statement.on_conflict_do_update(
                index_elements=conflict_index,
                set_={name: table.c[name] + value for name, value in values.items()},
            )
        )
    session.commit()


def _merge_without_tenant(
    session: Session, key: tuple, window_size: str, values: dict[str, Any]
) -> None:
    _, window_start, template, method, status_code = key
    row = session.scalar(
        select(ApiLatencyWindow).where(
            ApiLatencyWindow.tenant_id.is_(None),
            ApiLatencyWindow.window_start == window_start,
            ApiLatencyWindow.window_size == window_size,
            ApiLatencyWindow.route_template == template,
            ApiLatencyWindow.method == method,
            ApiLatencyWindow.status_code == status_code,
        )
    )
    if row is None:
        session.add(
            ApiLatencyWindow(
                window_start=window_start,
                window_size=window_size,
                route_template=template,
                method=method,
                status_code=status_code,
                **values,
            )
        )
        return
    for name, value in values.items():
        if name == "overhead_max_ms":
            setattr(row, name, max(float(getattr(row, name) or 0.0), float(value)))
        else:
            setattr(row, name, (getattr(row, name) or 0) + value)


class LatencyMetricsMiddleware:
    """ASGI middleware que mide cada request HTTP.

    Se registra en `main.py` con `app.add_middleware(LatencyMetricsMiddleware)`.
    No toca `WORKERS_ENABLED`, ni el routing, ni el cuerpo: mira el reloj y anota.
    Cualquier error suyo se traga, porque un fallo de observabilidad no puede
    convertirse en un 500 de negocio.
    """

    def __init__(self, app: Any, recorder: LatencyRecorder | None = None) -> None:
        self.app = app
        self._recorder = recorder
        self.last_overhead_ms = 0.0

    def recorder_for(self) -> LatencyRecorder | None:
        """Un recorder inyectado es una activacion explicita: manda sobre el flag.

        `config.latency_enabled()` gobierna el recorder GLOBAL (el que se
        registraria solo en produccion). Si alguien pasa uno a proposito -- un
        test, o un proceso que quiere medir sin tocar el entorno -- esa es la
        decision y el flag no la veta; al reves, un flag apagado tiene que
        respectarse.
        """
        if self._recorder is not None:
            return self._recorder
        if not config.latency_enabled():
            return None
        return shared_recorder()

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        recorder = self.recorder_for()
        if recorder is None:
            await self.app(scope, receive, send)
            return
        entered = time.perf_counter()
        state = {"code": 500}

        async def send_wrapper(message: dict) -> None:
            if message.get("type") == "http.response.start":
                code = message.get("status")
                if isinstance(code, int):
                    state["code"] = code
            await send(message)

        downstream_entered = time.perf_counter()
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            # El reloj del downstream se para ANTES de anotar: el tiempo de
            # anotar es nuestro, y metido en la duracion seria el
            # instrumentador midiendose a si mismo.
            downstream_done = time.perf_counter()
            pre_ms = (downstream_entered - entered) * 1000.0
            mark = time.perf_counter()
            self._observe(
                scope=scope,
                recorder=recorder,
                entered=entered,
                downstream_done=downstream_done,
                status_code=int(state["code"]),
                overhead_ms=pre_ms,
            )
            self.last_overhead_ms = pre_ms + (time.perf_counter() - mark) * 1000.0

    def _observe(
        self,
        *,
        scope: dict,
        recorder: LatencyRecorder,
        entered: float,
        downstream_done: float,
        status_code: int,
        overhead_ms: float,
    ) -> None:
        try:
            path = scope.get("path") or "/"
            template = recorder.normalize_route(scope, path)
            request_state = scope.get("state") or {}
            tenant = request_state.get(TENANT_STATE_KEY)
            recorder.record(
                Observation(
                    tenant_id=tenant if isinstance(tenant, int) else None,
                    window_start=stats.window_start(utcnow_naive(), recorder.window_size),
                    window_size=recorder.window_size,
                    route_template=template,
                    method=str(scope.get("method") or "GET")[:10],
                    status_code=status_code,
                    duration_ms=(downstream_done - entered) * 1000.0,
                    error=status_code >= 500,
                    overhead_ms=overhead_ms,
                )
            )
        except Exception:  # noqa: BLE001 — nunca romper el request por medirlo
            logger.debug("observacion de latencia fallida", exc_info=True)


_shared: LatencyRecorder | None = None
_shared_lock = threading.Lock()


def shared_recorder() -> LatencyRecorder:
    global _shared
    with _shared_lock:
        if _shared is None:
            _shared = LatencyRecorder()
        return _shared


def rows_for_window(
    db: Session, *, window_start: datetime, window_size: str
) -> list[ApiLatencyWindow]:
    """Filas de una ventana. El scope de tenant lo pone la sesion (con_loader)."""
    statement = (
        select(ApiLatencyWindow)
        .where(
            ApiLatencyWindow.window_start == window_start,
            ApiLatencyWindow.window_size == window_size,
        )
        .order_by(ApiLatencyWindow.request_count.desc())
    )
    return list(db.scalars(statement).all())


def latency_summary(rows: Sequence[ApiLatencyWindow]) -> dict:
    """Percentiles y agregados de un conjunto de filas.

    Se agregan los HISTOGRAMAS y no las medias, porque las filas tienen distinto
    numero de peticiones: promediar medias pondera igual una ruta con 3 samples
    que una con 3.000.
    """
    total = sum(int(row.request_count or 0) for row in rows)
    errors = sum(int(row.error_count or 0) for row in rows)
    if total <= 0:
        vacio = stats.indisponible("sin peticiones en la ventana")
        return {
            "requests": 0,
            "errors": 0,
            "error_rate": dict(vacio),
            "p50_ms": dict(vacio),
            "p95_ms": dict(vacio),
            "p99_ms": dict(vacio),
            "avg_ms": dict(vacio),
            "max_ms": stats.indisponible(
                "el histograma no guarda el maximo exacto, solo el tope de su ultimo cajon"
            ),
            "percentil_metodo": PERCENTILE_METHOD,
            "overhead": stats.indisponible("sin muestras de sobrecarga"),
        }
    buckets = [0] * len(LATENCY_BUCKET_EDGES)
    overflow = 0
    duration_sum = 0.0
    overhead_samples = 0
    overhead_sum = 0.0
    overhead_max = 0.0
    for row in rows:
        for index, name in enumerate(LATENCY_BUCKET_COLUMNS):
            buckets[index] += int(getattr(row, name) or 0)
        overflow += int(row.overflow or 0)
        duration_sum += float(row.duration_sum_ms or 0.0)
        overhead_samples += int(row.overhead_samples or 0)
        overhead_sum += float(row.overhead_sum_ms or 0.0)
        overhead_max = max(overhead_max, float(row.overhead_max_ms or 0.0))
    max_block = stats.disponible(LATENCY_BUCKET_EDGES[-1])
    if overflow > 0:
        max_block = stats.indisponible(
            f"{overflow} peticiones por encima de {LATENCY_BUCKET_EDGES[-1]} ms; "
            "el maximo exacto no esta en el histograma"
        )
    overhead_value = (
        {"avg_ms": overhead_sum / overhead_samples, "max_ms": overhead_max,
         "samples": overhead_samples}
        if overhead_samples
        else None
    )
    return {
        "requests": total,
        "errors": errors,
        "error_rate": stats.disponible(errors / total),
        "p50_ms": stats.disponible(
            stats.percentile_from_histogram(LATENCY_BUCKET_EDGES, buckets, overflow, 0.50)
        ),
        "p95_ms": stats.disponible(
            stats.percentile_from_histogram(LATENCY_BUCKET_EDGES, buckets, overflow, 0.95)
        ),
        "p99_ms": stats.disponible(
            stats.percentile_from_histogram(LATENCY_BUCKET_EDGES, buckets, overflow, 0.99)
        ),
        "avg_ms": stats.disponible(duration_sum / total),
        "max_ms": max_block,
        "percentil_metodo": PERCENTILE_METHOD,
        "histograma": stats.histogram_from_buckets(LATENCY_BUCKET_EDGES, buckets),
        "histograma_overflow": overflow,
        "overhead": (
            stats.disponible(overhead_value)
            if overhead_value is not None
            else stats.indisponible("el middleware no registro muestras en esta ventana")
        ),
    }


def by_route(rows: Sequence[ApiLatencyWindow], limit: int, offset: int) -> dict:
    """Latencia agrupada por plantilla de ruta, paginada."""
    grouped: dict[str, list[ApiLatencyWindow]] = {}
    for row in rows:
        grouped.setdefault(row.route_template, []).append(row)
    ordered = sorted(
        grouped.items(),
        key=lambda item: sum(int(r.request_count or 0) for r in item[1]),
        reverse=True,
    )
    page = ordered[offset: offset + limit]
    return {
        "total_series": len(ordered),
        "limit": limit,
        "offset": offset,
        "rutas": [
            {
                "route_template": template,
                "methods": sorted({row.method for row in group}),
                "status_codes": sorted({row.status_code for row in group}),
                **latency_summary(group),
            }
            for template, group in page
        ],
    }


def count_rows(db: Session, window_size: str) -> int:
    statement = select(func.count()).select_from(ApiLatencyWindow).where(
        ApiLatencyWindow.window_size == window_size
    )
    return int(db.scalar(statement) or 0)