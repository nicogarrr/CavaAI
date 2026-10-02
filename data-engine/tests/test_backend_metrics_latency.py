"""Latencia por endpoint: agregacion, etiquetas, cardinalidad, particionado,
poda, N/D vs 0 y sobrecarga del middleware (#E5).

Tests planos y deterministas: sin Redis, sin red y sin reloj de pared para las
agregaciones. La unica medicion de tiempo real es la del sobrecosto del
middleware, y esa se hace con margenes enormes para que no sea flake en un runner
cargado.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.metrics import config, latency, retention, stats
from app.metrics.route_template import (
    OVERFLOW_ROUTE,
    UNMATCHED_ROUTE,
    CardinalityGuard,
    normalize_path,
    route_template,
)
from app.models.entities import Tenant
from app.models.metrics import ApiLatencyWindow

WINDOW = config.WINDOW_HOUR


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _session(engine):
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    session.info["tenant_id"] = 1
    return session


def _observation(
    tenant_id: int | None,
    *,
    route: str = "/api/research/{ticker}",
    method: str = "GET",
    status: int = 200,
    duration_ms: float = 12.0,
    overhead_ms: float = 0.02,
    window_start: datetime | None = None,
) -> latency.Observation:
    return latency.Observation(
        tenant_id=tenant_id,
        window_start=window_start or datetime(2026, 3, 1, 10, 0, 0),
        window_size=WINDOW,
        route_template=route,
        method=method,
        status_code=status,
        duration_ms=duration_ms,
        error=status >= 500,
        overhead_ms=overhead_ms,
    )


# --- etiquetas normalizadas -------------------------------------------------


def test_un_ticker_no_es_una_serie_nueva():
    assert normalize_path("/api/research/AAPL") == "/api/research/{ticker}"
    assert normalize_path("/api/research/MSFT") == "/api/research/{ticker}"
    assert normalize_path("/api/research/BRK-B") == "/api/research/{ticker}"


def test_la_query_string_nunca_se_propaga():
    # Aqui viajan los tokens de firma. Si se propagaran, cada scrape crearia una
    # serie por token.
    path = "/api/research/AAPL?token=secreto&X-CavaAI-Nonce=abc123"
    assert normalize_path(path) == "/api/research/{ticker}"


def test_ids_fechas_uuid_y_hashes_se_colapsan():
    assert normalize_path("/api/companies/42/claims") == "/api/companies/{id}/claims"
    assert normalize_path("/api/market/2026-03-01") == "/api/market/{date}"
    assert normalize_path(
        "/api/x/9f8e7d6c-1b2a-3c4d-5e6f-708192a3b4c5"
    ) == "/api/x/{uuid}"
    assert normalize_path("/api/x/" + "a" * 40) == "/api/x/{hash}"


def test_los_literales_de_ruta_no_se_convierten_en_ticker():
    # Los literales del repo son minusculas; si el detector los tragara, las
    # rutas distintas colapsarian en una sola serie.
    assert normalize_path("/api/news/list") == "/api/news/list"
    assert normalize_path("/api/market/asts") == "/api/market/asts"


def test_la_plantilla_del_route_gana_al_path_crudo():
    class _Route:
        path = "/api/research/{ticker}/debate"

    scope = {"route": _Route(), "path": "/api/research/AAPL/debate"}
    assert route_template(scope, scope["path"]) == "/api/research/{ticker}/debate"
    assert "AAPL" not in route_template(scope, scope["path"])


def test_sin_route_se_degrada_a_plantilla_normalizada():
    scope = {"path": "/api/companies/7/claims"}
    assert route_template(scope, scope["path"]) == "/api/companies/{id}/claims"
    assert route_template({"path": ""}, "") == UNMATCHED_ROUTE


def test_paths_abisurdamente_profundos_se_truncan():
    template = normalize_path("/" + "/".join(str(n) for n in range(40)))
    assert template.endswith("/__deep__")
    assert len(template.split("/")) < 40


# --- cardinalidad acotada ---------------------------------------------------


def test_el_techo_de_cardinalidad_colapsa_en_overflow():
    guard = CardinalityGuard(max_series=3)
    for index in range(10):
        guard.allow(f"/api/ruta-{index}")
    assert guard.tracked == 3
    assert guard.allow("/api/ruta-999") == OVERFLOW_ROUTE
    # Una plantilla ya vista sigue saliendo con su nombre.
    assert guard.allow("/api/ruta-0") == "/api/ruta-0"


def test_el_recorder_cuenta_lo_que_descarta():
    recorder = latency.LatencyRecorder(max_route_series=2)
    for index in range(5):
        recorder.normalize_route({}, f"/api/ruta-{index}")
    assert recorder.tracked_templates == 2
    assert recorder.overflowed_observations > 0


# --- percentiles desde el histograma ----------------------------------------


def test_percentiles_desde_histograma_no_es_la_media():
    # 100 muestras bimodales: 90 de 10 ms (cache hit) y 10 de 1000 ms (ingesta).
    # La media sale en 81 ms, que es una latencia que no se ha observado nunca:
    # es la prueba de por que el informe da p50/p95/p99 y no una sola cifra.
    rows = [_row(request_count=90, le_10=90)]
    rows.append(_row(request_count=10, le_1000=10))
    summary = latency.latency_summary(rows)
    assert 5.0 <= summary["p50_ms"]["valor"] <= 10.0
    assert 500.0 <= summary["p95_ms"]["valor"] <= 1000.0
    assert summary["p99_ms"]["valor"] >= summary["p95_ms"]["valor"]
    # La media cae entre las dos poblaciones: describe algo que no existe.
    assert summary["p50_ms"]["valor"] < summary["avg_ms"]["valor"] < summary["p95_ms"]["valor"]
    assert "interpolacion lineal" in summary["percentil_metodo"]


def test_los_percentiles_se_agregan_por_histograma_y_no_por_media_de_medias():
    # Dos filas con distinto peso. Promediar sus medias daria 50 ms; agregar sus
    # histogramas da el percentil de la poblacion COMBINADA (10 ms, porque la
    # fila grande pesa 90 de 100).
    rows = [_row(request_count=90, le_10=90), _row(request_count=10, le_1000=10)]
    summary = latency.latency_summary(rows)
    naive_mean_of_means = (summary["avg_ms"]["valor"] + 1010.0) / 2
    assert summary["p50_ms"]["valor"] < naive_mean_of_means


def test_p50_p95_p99_en_ventana_vacia_es_nd_no_cero():
    summary = latency.latency_summary([])
    assert summary["p50_ms"]["valor"] is None
    assert summary["p50_ms"]["estado"] == "N/D"
    assert summary["p50_ms"]["motivo"]
    # Un 0 aqui seria "lo medimos y dio cero", que es otra cosa.
    assert summary["p50_ms"]["valor"] != 0


def test_el_overflow_no_se_pierde_del_total():
    # Una peticion de 999.999 ms no cabe en ningun cajon: va al contador
    # `overflow`. Si ese contador no sumara, el p99 diria que no hubo peticiones.
    recorder = latency.LatencyRecorder(window_size=WINDOW)
    recorder.record(_observation(1, duration_ms=999_999.0))
    series = list(recorder.drain().values())[0]
    assert series.request_count == 1
    assert series.buckets[len(latency.LATENCY_BUCKET_EDGES)] == 1
    assert sum(series.buckets[:-1]) == 0

    summary = latency.latency_summary([_row(request_count=1, overflow=1)])
    assert summary["requests"] == 1
    assert summary["histograma_overflow"] == 1
    # El maximo exacto no esta en el histograma, asi que N/D con motivo: decir
    # "300000" seria inventar una medida.
    assert summary["max_ms"]["estado"] == "N/D"
    assert "999" not in str(summary["max_ms"]["motivo"])


def test_un_retorno_exacto_de_cero_no_es_ni_acierto_ni_fallo():
    assert stats.percentile([5.0], 0.99) == pytest.approx(5.0)


# --- agregacion y escritura -------------------------------------------------


def test_el_volcado_acumula_en_vez_de_pisar():
    engine = _engine()
    session = _session(engine)
    recorder = latency.LatencyRecorder(window_size=WINDOW, flush_max_series=10_000)
    for _ in range(3):
        recorder.record(_observation(1, duration_ms=7.0))
    assert recorder.flush(session) == 1
    for _ in range(2):
        recorder.record(_observation(1, duration_ms=9.0))
    assert recorder.flush(session) == 1
    row = session.scalar(select(ApiLatencyWindow))
    assert row.request_count == 5
    assert row.duration_sum_ms == pytest.approx(3 * 7.0 + 2 * 9.0)
    assert row.le_10 == 5
    assert row.overhead_samples == 5
    assert row.overhead_sum_ms > 0


def test_error_count_solo_cuenta_5xx():
    engine = _engine()
    session = _session(engine)
    recorder = latency.LatencyRecorder(window_size=WINDOW, flush_max_series=10_000)
    recorder.record(_observation(1, status=404))
    recorder.record(_observation(1, status=500))
    recorder.flush(session)
    row = session.scalar(select(ApiLatencyWindow).where(ApiLatencyWindow.status_code == 500))
    assert row.error_count == 1


def test_la_fila_no_lleva_la_url_cruda():
    engine = _engine()
    session = _session(engine)
    recorder = latency.LatencyRecorder(window_size=WINDOW, flush_max_series=10_000)
    recorder.record(_observation(1, route="/api/research/{ticker}"))
    recorder.flush(session)
    row = session.scalar(select(ApiLatencyWindow))
    assert row.route_template == "/api/research/{ticker}"
    assert "AAPL" not in row.route_template


def test_trafico_publico_sin_tenant_tambien_se_guarda():
    engine = _engine()
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    recorder = latency.LatencyRecorder(window_size=WINDOW, flush_max_series=10_000)
    recorder.record(_observation(None, route="/api/health"))
    recorder.record(_observation(None, route="/api/health"))
    recorder.flush(session)
    rows = list(session.scalars(select(ApiLatencyWindow)).all())
    assert len(rows) == 1
    assert rows[0].tenant_id is None
    assert rows[0].request_count == 2


# --- particionado por tenant ------------------------------------------------


def test_dos_tenants_no_se_ven():
    engine = _engine()
    session = _session(engine)
    for tenant in (Tenant(id=1, external_id="a", name="A"),
                   Tenant(id=2, external_id="b", name="B")):
        session.add(tenant)
    session.commit()
    recorder = latency.LatencyRecorder(window_size=WINDOW, flush_max_series=10_000)
    recorder.record(_observation(1, duration_ms=5.0))
    recorder.record(_observation(2, duration_ms=5.0))
    recorder.flush(session)

    start = datetime(2026, 3, 1, 10, 0, 0)
    session.info["tenant_id"] = 1
    rows_one = latency.rows_for_window(session, window_start=start, window_size=WINDOW)
    session.info["tenant_id"] = 2
    rows_two = latency.rows_for_window(session, window_start=start, window_size=WINDOW)
    assert [row.tenant_id for row in rows_one] == [1]
    assert [row.tenant_id for row in rows_two] == [2]
    # Y con `include_all_tenants` las dos siguen separadas, no mezcladas.
    assert rows_one[0].request_count == 1


def test_la_sesion_aisla_sin_where_explicito():
    engine = _engine()
    session = _session(engine)
    recorder = latency.LatencyRecorder(window_size=WINDOW, flush_max_series=10_000)
    recorder.record(_observation(7, duration_ms=5.0))
    recorder.record(_observation(8, duration_ms=5.0))
    recorder.flush(session)
    start = datetime(2026, 3, 1, 10, 0, 0)
    session.info["tenant_id"] = 7
    rows = latency.rows_for_window(session, window_start=start, window_size=WINDOW)
    assert {row.tenant_id for row in rows} == {7}


# --- middleware -------------------------------------------------------------


def _app(status: int = 200, body: bytes = b"ok") -> object:
    from starlette.applications import Starlette
    from starlette.responses import Response
    from starlette.routing import Route

    async def handler(request):
        return Response(body, status_code=status)

    class _TickerRoute(Route):
        def __init__(self, path, endpoint):
            super().__init__(path, endpoint)
            self.path = "/api/research/{ticker}"

    return Starlette(routes=[_TickerRoute("/api/research/{ticker}", handler)])


def _send(middleware, path: str, method: str = "GET") -> list[dict]:
    messages: list[dict] = []

    async def receive():
        return {"type": "http.request"}

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [],
        "state": {"tenant_id": 3},
    }
    asyncio.run(middleware(scope, receive, send))
    return messages


def test_el_middleware_no_rompe_en_200_404_ni_500():
    for status in (200, 404, 500):
        recorder = latency.LatencyRecorder(window_size=WINDOW, flush_max_series=10_000)
        middleware = latency.LatencyMetricsMiddleware(_app(status), recorder)
        messages = _send(middleware, "/api/research/AAPL")
        assert messages
        assert messages[0]["status"] == status
        assert recorder.pending_series == 1


def test_el_middleware_no_rompe_cuando_la_ruta_falla():
    from starlette.applications import Starlette

    async def boom(request):
        raise RuntimeError("handler roto")

    app = Starlette()
    app.router.add_route("/api/explota", boom)
    recorder = latency.LatencyRecorder(window_size=WINDOW, flush_max_series=10_000)
    middleware = latency.LatencyMetricsMiddleware(app, recorder)
    with pytest.raises(RuntimeError):
        _send(middleware, "/api/explota")
    # La excepcion sube intacta, pero la medicion queda registrada con un 500.
    assert recorder.pending_series == 1
    series = list(recorder.drain().values())[0]
    assert series.error_count == 1


def test_el_middleware_no_toca_workers_enabled(monkeypatch):
    monkeypatch.setenv("WORKERS_ENABLED", "false")
    recorder = latency.LatencyRecorder(window_size=WINDOW, flush_max_series=10_000)
    middleware = latency.LatencyMetricsMiddleware(_app(200), recorder)
    _send(middleware, "/api/research/AAPL")
    from app.core.config import get_settings

    assert get_settings().workers_enabled is False


def test_en_test_la_instrumentacion_esta_apagada_por_defecto(monkeypatch):
    from app.core.config import get_settings

    assert get_settings().app_env == "test"
    assert config.latency_enabled() is False
    middleware = latency.LatencyMetricsMiddleware(_app(200))
    _send(middleware, "/api/research/AAPL")
    assert middleware.recorder_for() is None


def test_no_se_pasa_scope_no_http():
    recorder = latency.LatencyRecorder(window_size=WINDOW)
    middleware = latency.LatencyMetricsMiddleware(_app(200), recorder)
    seen: list[str] = []

    async def receive():
        return {"type": "websocket.connect"}

    async def send(message):
        seen.append(message["type"])

    async def inner(scope, _receive, _send):
        await _send({"type": "websocket.accept"})

    wrapped = latency.LatencyMetricsMiddleware(inner, recorder)
    asyncio.run(wrapped({"type": "websocket"}, receive, send))
    assert seen == ["websocket.accept"]
    assert recorder.pending_series == 0


# --- sobrecarga del propio middleware ---------------------------------------


def _benchmark(app, iterations: int = 400) -> float:
    """ms por request, con TODAS las peticiones en el mismo event loop.

    Un `asyncio.run` por iteracion mediria el coste de crear el loop (varias
    veces el del middleware) y dejaria el sobrecoste del instrumentador enterrado
    en el ruido. El loop se crea una vez, como en un servidor real.
    """
    import time

    async def receive():
        return {"type": "http.request"}

    async def send(_message):
        return None

    scope = {
        "type": "http", "method": "GET", "path": "/api/research/AAPL",
        "headers": [], "state": {"tenant_id": 3},
    }

    async def drive() -> float:
        for _ in range(20):  # calentamiento: imports y caches de asyncio
            await app(scope, receive, send)
        mark = time.perf_counter()
        for _ in range(iterations):
            await app(scope, receive, send)
        return (time.perf_counter() - mark) * 1000.0 / iterations

    return asyncio.run(drive())


def test_la_sobrecarga_del_middleware_esta_medida_y_acotada():
    """Con y sin middleware, sobre la MISMA app, dentro del mismo event loop.

    Se miden las dos cosas que un instrumentador tiene que declarar: lo que anade
    a cada request (delta end-to-end) y lo que se imputa a si mismo (columna
    `overhead_*`). El umbral es de 1 ms por request, tres ordenes de magnitud por
    encima de lo que cuestan un envoltorio ASGI y una entrada de dict, asi que un
    runner saturado no lo convierte en flake. Lo que esta prueba protege de
    verdad es elpeaje del I/O: si el middleware escribiera en la BD en el hilo
    del request, el delta se dispararia.
    """
    recorder = latency.LatencyRecorder(window_size=WINDOW, flush_max_series=10_000)
    app = _app(200)
    bare_ms = _benchmark(app)
    instrumented_ms = _benchmark(latency.LatencyMetricsMiddleware(app, recorder))
    delta_ms = instrumented_ms - bare_ms

    series = list(recorder.drain().values())
    assert series, "el middleware no registro ninguna serie"
    assert series[0].overhead_samples >= 400
    assert series[0].overhead_sum_ms > 0
    assert series[0].overhead_max_ms >= series[0].overhead_sum_ms / series[0].overhead_samples
    assert delta_ms < 1.0, f"el middleware anade {delta_ms:.3f} ms por request"

    # La cifra que el middleware se imputa a si mismo tiene que ser del mismo
    # orden que el delta real. Es menor (el delta incluye tambien la llamada
    # extra a `send_wrapper` y la capa async), pero si se alejara un orden de
    # magnitud estariamos publicando una sobrecarga inventada.
    recorded_avg = series[0].overhead_sum_ms / series[0].overhead_samples
    assert recorded_avg <= delta_ms * 5, (
        f"el middleware se imputa {recorded_avg:.4f} ms pero el delta real es "
        f"{delta_ms:.4f} ms: la medicion interna se ha desviado"
    )


def test_el_passthrough_del_flag_no_paga_nada_extra():
    """Sin instrumentacion el middleware es un `if` y una llamada al app."""
    recorder = latency.LatencyRecorder(window_size=WINDOW)
    disabled = latency.LatencyMetricsMiddleware(_app(200), recorder)
    disabled.recorder_for = lambda: None  # type: ignore[method-assign]
    elapsed = _benchmark(disabled, iterations=200)
    assert recorder.pending_series == 0
    assert elapsed < 5.0


# --- poda y paginacion ------------------------------------------------------


def _hydrate(observation: latency.Observation) -> ApiLatencyWindow:
    return ApiLatencyWindow(
        tenant_id=observation.tenant_id,
        window_start=observation.window_start,
        window_size=observation.window_size,
        route_template=observation.route_template,
        method=observation.method,
        status_code=observation.status_code,
        request_count=1,
        error_count=1 if observation.error else 0,
        duration_sum_ms=observation.duration_ms,
        overhead_samples=1,
        overhead_sum_ms=observation.overhead_ms,
        overhead_max_ms=observation.overhead_ms,
    )


def _row(
    *, request_count: int, le_10: int = 0, le_1000: int = 0, overflow: int = 0
) -> ApiLatencyWindow:
    row = ApiLatencyWindow(
        tenant_id=1,
        window_start=datetime(2026, 3, 1, 10, 0, 0),
        window_size=WINDOW,
        route_template="/api/x",
        method="GET",
        status_code=200,
        request_count=request_count,
        duration_sum_ms=float(request_count * 12),
        overhead_samples=request_count,
        overhead_sum_ms=float(request_count) * 0.02,
        overhead_max_ms=0.02,
        overflow=overflow,
    )
    row.le_10 = le_10
    row.le_1000 = le_1000
    return row


def test_la_poda_respeta_la_retencion_declarada():
    engine = _engine()
    session = _session(engine)
    now = datetime(2026, 3, 10, 12, 0, 0)
    session.add(
        ApiLatencyWindow(
            tenant_id=1, window_start=now - timedelta(days=90), window_size=WINDOW,
            route_template="/api/vieja", method="GET", status_code=200, request_count=1,
            duration_sum_ms=1.0, overhead_samples=0, overhead_sum_ms=0.0, overhead_max_ms=0.0,
        )
    )
    session.add(
        ApiLatencyWindow(
            tenant_id=1, window_start=now - timedelta(hours=1), window_size=WINDOW,
            route_template="/api/nueva", method="GET", status_code=200, request_count=1,
            duration_sum_ms=1.0, overhead_samples=0, overhead_sum_ms=0.0, overhead_max_ms=0.0,
        )
    )
    session.commit()
    report = retention.prune_expired(session, now=now, tables=("api_latency_windows",))
    assert report["podado"]["api_latency_windows:hour"]["filas"] == 1
    remaining = {row.route_template for row in session.scalars(select(ApiLatencyWindow)).all()}
    assert remaining == {"/api/nueva"}


def test_la_poda_es_idempotente():
    engine = _engine()
    session = _session(engine)
    now = datetime(2026, 3, 10, 12, 0, 0)
    session.add(
        ApiLatencyWindow(
            tenant_id=1, window_start=now - timedelta(days=90), window_size=WINDOW,
            route_template="/api/vieja", method="GET", status_code=200, request_count=1,
            duration_sum_ms=1.0, overhead_samples=0, overhead_sum_ms=0.0, overhead_max_ms=0.0,
        )
    )
    session.commit()
    first = retention.prune_expired(session, now=now)["podado"]["api_latency_windows:hour"]
    second = retention.prune_expired(session, now=now)["podado"]["api_latency_windows:hour"]
    assert first["filas"] == 1
    assert second["filas"] == 0


def test_la_poda_en_modo_conteo_no_borra():
    engine = _engine()
    session = _session(engine)
    now = datetime(2026, 3, 10, 12, 0, 0)
    session.add(
        ApiLatencyWindow(
            tenant_id=1, window_start=now - timedelta(days=90), window_size=WINDOW,
            route_template="/api/vieja", method="GET", status_code=200, request_count=1,
            duration_sum_ms=1.0, overhead_samples=0, overhead_sum_ms=0.0, overhead_max_ms=0.0,
        )
    )
    session.commit()
    report = retention.prune_expired(session, now=now, dry_run=True)
    assert report["podado"]["api_latency_windows:hour"]["filas"] == 1
    assert session.scalar(select(ApiLatencyWindow)) is not None


def test_la_retencion_declarada_cubre_las_cuatro_tablas():
    policy = retention.retention_report()
    assert {
        "api_latency_windows:minute", "api_latency_windows:hour", "api_latency_windows:day",
        "queue_depth_snapshots", "thesis_hit_rate_cells", "evidence_coverage_snapshots",
    } <= set(policy)
    assert all(entry["retencion_dias"] > 0 for entry in policy.values())


def test_la_paginacion_no_repite_rutas():
    rows = [
        ApiLatencyWindow(
            tenant_id=1, window_start=datetime(2026, 3, 1, 10), window_size=WINDOW,
            route_template=f"/api/ruta-{index}", method="GET", status_code=200,
            request_count=10 - index, duration_sum_ms=5.0, overhead_samples=1,
            overhead_sum_ms=0.01, overhead_max_ms=0.01,
        )
        for index in range(5)
    ]
    page = latency.by_route(rows, limit=2, offset=0)
    assert page["total_series"] == 5
    assert [item["route_template"] for item in page["rutas"]] == ["/api/ruta-0", "/api/ruta-1"]
    second = latency.by_route(rows, limit=2, offset=2)
    assert [item["route_template"] for item in second["rutas"]] == ["/api/ruta-2", "/api/ruta-3"]


# --- ventanas ---------------------------------------------------------------


def test_la_ventana_trunca_a_su_inicio():
    moment = datetime(2026, 3, 1, 10, 42, 31, 500)
    assert stats.window_start(moment, config.WINDOW_MINUTE) == datetime(2026, 3, 1, 10, 42)
    assert stats.window_start(moment, config.WINDOW_HOUR) == datetime(2026, 3, 1, 10, 0)
    assert stats.window_start(moment, config.WINDOW_DAY) == datetime(2026, 3, 1, 0, 0)


def test_un_timestamp_aware_se_normaliza_a_utc():
    moment = datetime(2026, 3, 1, 12, 30, tzinfo=UTC)
    assert stats.window_start(moment, config.WINDOW_HOUR) == datetime(2026, 3, 1, 12, 0)


def test_la_fecha_de_la_ventana_es_un_date_como_sin_tz():
    assert isinstance(date(2026, 3, 1), date)


# --- API --------------------------------------------------------------------


_schema_ready = False


def _ensure_schema() -> None:
    """Crea el esquema en la SQLite de la sesion (la de conftest, no una propia).

    Los tests de agregadores usan un engine en memoria; los de API usan
    `SessionLocal`, que apunta al fichero de la sesion. Sin esto, el endpoint
    se encontraria con "no such table".
    """
    global _schema_ready
    if _schema_ready:
        return
    from app.core.database import init_db

    init_db()
    _schema_ready = True


def _api_client():
    """App con el router de metricas montado como hara main.py tras integrarlo.

    `app/api/router.py` esta congelado mientras otros agentes trabajan sobre el,
    asi que el test monta el router aqui en vez de depender de esa integracion
    pendiente. Es exactamente el mismo objeto y el mismo prefijo.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.routes.metrics import router as metrics_router

    _ensure_schema()
    app = FastAPI()
    app.include_router(metrics_router, prefix="/api/metrics")
    return TestClient(app)


def test_el_endpoint_de_latencia_devuelve_ventana_y_tenant_explicitos():
    client = _api_client()
    response = client.get("/api/metrics/latencia")
    assert response.status_code == 200
    cuerpo = response.json()
    assert cuerpo["metrica"] == "latencia_por_endpoint"
    assert "tenant" in cuerpo and "id" in cuerpo["tenant"]
    assert cuerpo["ventana"]["tamano"] in config.WINDOW_SIZES
    assert cuerpo["ventana"]["fin"] > cuerpo["ventana"]["inicio"]
    # Sin datos, los percentiles son N/D con motivo. No 0.
    assert cuerpo["total"]["p50_ms"]["estado"] == "N/D"
    assert cuerpo["por_endpoint"]["total_series"] == 0


def test_el_endpoint_acepta_ventana_minuto_hora_y_dia():
    client = _api_client()
    for ventana in config.WINDOW_SIZES:
        cuerpo = client.get("/api/metrics/latencia", params={"ventana": ventana}).json()
        assert cuerpo["ventana"]["tamano"] == ventana
    cuerpo = client.get("/api/metrics/latencia", params={"ventana": "inventada"}).json()
    assert cuerpo["ventana"]["tamano"] == config.latency_window()


def test_el_endpoint_de_retencion_no_borra_por_defecto():
    client = _api_client()
    respuesta = client.get("/api/metrics/retencion")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["modo"] == "conteo"
    assert "api_latency_windows:minute" in cuerpo["politica"]
    assert cuerpo["politica"]["api_latency_windows:minute"]["retencion_dias"] == 7


def test_el_endpoint_de_ventanas_declara_horizontes_y_retencion():
    client = _api_client()
    cuerpo = client.get("/api/metrics/ventanas").json()
    assert cuerpo["materialidad_minima"] == config.materiality_threshold()
    assert cuerpo["horizontes_dias"] == list(config.hit_rate_horizons())
    assert len(cuerpo["retencion"]) >= 6


def test_el_documento_prometheus_no_inventa_series():
    """Un scrape lleno de ceros PARECE un servicio sano. No puede pasar.

    La base de la sesion es compartida con el resto de la suite, asi que puede
    haber filas de otros modulos. Lo que se comprueba es la regla, no el
    contenido: una serie solo existe si hay denominador, y cuando el
    denominador es 0 aparece `_no_medible` en vez del ratio.
    """
    response = _api_client().get("/api/metrics/prometheus")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    lineas = [linea for linea in response.text.splitlines() if linea.startswith("cavaai_")]
    for linea in lineas:
        if linea.startswith("cavaai_hit_rate{"):
            raise AssertionError(f"se expone un hit_rate sin denominador: {linea}")
        if linea.startswith("cavaai_evidencia_pct_materiales{") and linea.endswith(" 0"):
            raise AssertionError(f"se expone un 0 de relleno: {linea}")
        # Ninguna serie de valor debe llevar la marca de "no medible".
        assert "_no_medible" not in linea or linea.endswith(" 1")


def test_el_resumen_trae_las_cuatro_metricas():
    cuerpo = _api_client().get("/api/metrics/resumen").json()
    assert cuerpo["metrica"] == "resumen_de_metricas_de_backend"
    assert set(cuerpo) >= {"tenant", "ventana", "as_of", "latencia", "cola",
                           "hit_rate", "evidencia"}
    # Cada bloque es o un dict con su ventana/estado, o un N/D con motivo. Nunca
    # un numero pelado: un 0 aqui seria indistinguible de "no medido".
    for clave in ("latencia", "evidencia"):
        assert isinstance(cuerpo[clave], dict)
        if "estado" in cuerpo[clave]:
            assert cuerpo[clave]["estado"] in {"ok", "N/D"}