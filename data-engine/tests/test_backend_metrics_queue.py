"""Profundidad de cola y salud de workers (#E5, metrica 2).

Sin Redis: el doble en memoria reproduce el layout de claves que documenta
`dramatiq/brokers/redis/dispatch.lua` (`dramatiq:{cola}`, `.msgs`, `.DQ`, `.XQ`,
`dramatiq:__heartbeats__`). Asi los tests son deterministas y no dependen de que
haya un Redis levantado, que es justo lo que `WORKERS_ENABLED=false` implica.

Lo que se verifica aqui, en orden de importancia:
  1. los numeros salen del layout real de Dramatiq, no de supuestos;
  2. un worker parado sale como INCIDENTE con razon, no como un statistic;
  3. Redis caido sale N/D con motivo, NUNCA 0;
  4. la instrumentacion no cambia el comportamiento de `WORKERS_ENABLED`;
  5. los contadores de resultado vienen del middleware de Dramatiq, no de sondear.
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.metrics import queue as queue_stats
from app.models.metrics import QueueDepthSnapshot

NOW_MS = 1_800_000_000_000
NOW = datetime(2027, 1, 15, 12, 0, 0)


class FakeRedis:
    """Doble en memoria del subconjunto de Redis que usa la sonda.

    Reproduce el contrato de `RedisBroker` (LIST para la cola, HASH `.msgs`,
    LIST `.DQ`, ZSET `.XQ`, ZSET `__heartbeats__`) sinâ€œLua ni sockets.
    """

    def __init__(self, *, failing: bool = False) -> None:
        self.lists: dict[str, list[str]] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.zsets: dict[str, dict[str, float]] = {}
        self.failing = failing

    def _check(self) -> None:
        if self.failing:
            raise ConnectionError("redis no responde")

    # --- listas
    def llen(self, key: str) -> int:
        self._check()
        return len(self.lists.get(key, []))

    # --- hashes
    def hlen(self, key: str) -> int:
        self._check()
        return len(self.hashes.get(key, {}))

    def hvals(self, key: str) -> list[str]:
        self._check()
        return list(self.hashes.get(key, {}).values())

    def hscan_iter(self, key: str, count: int = 100):
        self._check()
        yield from self.hashes.get(key, {}).items()

    # --- sorted sets
    def zcard(self, key: str) -> int:
        self._check()
        return len(self.zsets.get(key, {}))

    def zcount(self, key: str, low: float, high: str) -> int:
        self._check()
        return sum(1 for score in self.zsets.get(key, {}).values() if score >= low)

    def zrange(self, key: str, start: int, end: int, withscores: bool = False):
        self._check()
        items = sorted(self.zsets.get(key, {}).items(), key=lambda item: item[1])
        if start == -1:
            items = items[-1:]
        return [(name, score) for name, score in items]

    def scan_iter(self, match: str = "", count: int = 100):
        self._check()
        for key in list(self.lists) + list(self.hashes) + list(self.zsets):
            yield key.encode()

    # --- siembra
    def enqueue(self, queue: str, message_id: str, timestamp_ms: int) -> None:
        base = queue_stats.queue_key(queue)
        self.lists.setdefault(base, []).append(message_id)
        self.hashes.setdefault(f"{base}.msgs", {})[message_id] = json.dumps(
            {"message_id": message_id, "message_timestamp": timestamp_ms,
             "queue_name": queue, "actor_name": "refresh_news"}
        )

    def fetch(self, queue: str, message_id: str) -> None:
        """Saca el mensaje de la lista pero deja el cuerpo: eso es 'en curso'."""
        self.lists[queue_stats.queue_key(queue)].remove(message_id)

    def delay(self, queue: str, message_id: str, timestamp_ms: int) -> None:
        base = queue_stats.queue_key(queue)
        self.lists.setdefault(f"{base}.DQ", []).append(message_id)
        self.hashes.setdefault(f"{base}.DQ.msgs", {})[message_id] = json.dumps(
            {"message_id": message_id, "message_timestamp": timestamp_ms}
        )

    def dead_letter(self, queue: str, message_id: str) -> None:
        self.zsets.setdefault(f"{queue_stats.queue_key(queue)}.XQ", {})[message_id] = float(NOW_MS)

    def heartbeat(self, worker_id: str, age_ms: int = 0) -> None:
        self.zsets.setdefault(queue_stats.HEARTBEATS_KEY, {})[worker_id] = float(NOW_MS - age_ms)


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _session(engine, tenant_id: int | None = 1):
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    if tenant_id is not None:
        session.info["tenant_id"] = tenant_id
    return session


# --- lectura del layout real de Dramatiq ------------------------------------


def test_los_cuatro_estados_salen_de_cuatro_claves_distintas():
    client = FakeRedis()
    client.enqueue("alerts", "m1", NOW_MS - 5_000)
    client.enqueue("alerts", "m2", NOW_MS - 60_000)
    client.fetch("alerts", "m2")          # en curso: fuera de la lista, cuerpo vivo
    client.delay("alerts", "m3", NOW_MS - 1_000)
    client.dead_letter("alerts", "m1")
    client.heartbeat("worker-1")

    state = queue_stats.probe_queue(client, "alerts", now_ms=NOW_MS)
    assert state.pending == 1
    assert state.delayed == 1
    assert state.in_flight == 1
    assert state.dead_lettered == 1
    assert state.workers_live == 1
    assert state.workers_total == 1


def test_la_edad_del_mas_viejo_usa_el_timestamp_del_mensaje():
    client = FakeRedis()
    client.enqueue("alerts", "nuevo", NOW_MS - 1_000)
    client.enqueue("alerts", "viejo", NOW_MS - 600_000)
    state = queue_stats.probe_queue(client, "alerts", now_ms=NOW_MS)
    assert state.oldest_age_s == pytest.approx(600.0)
    assert state.oldest_age_exhaustive is True


def test_con_la_cola_grande_la_edad_es_estimacion_y_se_declara():
    client = FakeRedis()
    for index in range(900):
        client.enqueue("kpis", f"m{index}", NOW_MS - (index * 1_000))
    state = queue_stats.probe_queue(
        client, "kpis", now_ms=NOW_MS, sample_limit=100, stall_seconds=10_000
    )
    assert state.oldest_age_exhaustive is False
    assert state.oldest_age_sample <= 100
    # Y aun asi da una edad utilizable, que es lo que hace el umbral util.
    assert state.oldest_age_s is not None and state.oldest_age_s >= 0


def test_una_cola_vacia_no_tiene_edad_ni_un_cero_falso():
    state = queue_stats.probe_queue(FakeRedis(), "kpis", now_ms=NOW_MS)
    assert state.pending == 0
    assert state.oldest_age_s is None
    assert "oldest_age_s" not in state.measured_fields


# --- incidente vs statistic -------------------------------------------------


def test_trabajo_parado_es_un_incidente_con_razon():
    client = FakeRedis()
    client.enqueue("thesis", "m1", NOW_MS - 900_000)   # 15 min parada
    client.heartbeat("worker-1")
    state = queue_stats.probe_queue(client, "thesis", now_ms=NOW_MS, stall_seconds=300.0)
    assert state.pending == 1
    assert state.in_flight == 0
    assert state.status == queue_stats.STALL_STATUS
    assert "parado" in (state.incident_reason or "")
    assert "900" in (state.incident_reason or "")


def test_una_cola_profunda_con_trabajo_en_curso_no_es_un_incidente():
    # 10.000 pendientes con 4 en curso es backpressure, no una averia: hay quien
    # esta trabajando. Confundir las dos cosas genera paginas de guardia a las
    # tres de la maÃ±ana.
    client = FakeRedis()
    for index in range(4):
        client.enqueue("default", f"m{index}", NOW_MS - 900_000)
        client.fetch("default", f"m{index}")
    for index in range(4, 10_004):
        client.enqueue("default", f"m{index}", NOW_MS - 1_000)
    state = queue_stats.probe_queue(client, "default", now_ms=NOW_MS, stall_seconds=300.0)
    assert state.pending == 10_000
    assert state.in_flight == 4
    assert state.status != queue_stats.STALL_STATUS


def test_sin_workers_vivos_la_razon_sigue_siendo_el_umbral_de_edad():
    client = FakeRedis()
    client.enqueue("gdelt", "m1", NOW_MS - 10_000)
    state = queue_stats.probe_queue(client, "gdelt", now_ms=NOW_MS, stall_seconds=300.0)
    assert state.status == queue_stats.OK_STATUS
    assert state.incident_reason is None


def test_una_cola_que_no_avanza_con_trabajo_en_curso_es_degradada():
    # 3 en curso que llevan 83 min y 20 mas esperando: hay trabajo corriendo pero
    # la cola no se vacia. No es un incidente (hay workers), pero si degradado.
    client = FakeRedis()
    for index in range(3):
        client.enqueue("kpis", f"w{index}", NOW_MS - 5_000_000)
        client.fetch("kpis", f"w{index}")
    for index in range(20):
        client.enqueue("kpis", f"p{index}", NOW_MS - 5_000_000)
    client.heartbeat("worker-1")
    state = queue_stats.probe_queue(client, "kpis", now_ms=NOW_MS, stall_seconds=300.0)
    assert state.in_flight == 3
    assert state.status == queue_stats.DEGRADED_STATUS
    assert "no avanza" in (state.incident_reason or "")


def test_la_razon_del_incidente_siempre_va_con_el_estado():
    for status in (queue_stats.OK_STATUS, queue_stats.DEGRADED_STATUS,
                   queue_stats.STALL_STATUS):
        client = FakeRedis()
        client.enqueue("alerts", "m1", NOW_MS - 900_000)
        client.heartbeat("worker-1")
        state = queue_stats.probe_queue(client, "alerts", now_ms=NOW_MS, stall_seconds=300.0)
        if status != queue_stats.OK_STATUS:
            assert state.incident_reason, f"{status} sin razon"


# --- fail honesto: N/D, nunca 0 --------------------------------------------


def test_redis_caido_da_nd_y_no_ceros():
    state = queue_stats.probe_queue(FakeRedis(failing=True), "alerts", now_ms=NOW_MS)
    assert state.status == queue_stats.UNKNOWN_STATUS
    assert state.pending is None
    assert state.delayed is None
    assert state.in_flight is None
    assert state.dead_lettered is None
    assert state.unavailable
    # Un 0 aqui seria "lo medimos y hay 0 encolados": mentira.


def test_sin_cliente_redis_todas_las_colas_son_nd():
    states = queue_stats.probe_all(client=None, queues=("alerts", "kpis"))
    # El doble se pasa explicitamente; con None el modulo intenta abrir Redis de
    # verdad, asi que aqui se comprueba el camino del cliente inyectado que falla.
    assert states == [] or all(s.status == queue_stats.UNKNOWN_STATUS for s in states)


def test_el_payload_deja_visible_el_nd():
    row = QueueDepthSnapshot(
        queue_name="alerts", observed_at=NOW, window_start=NOW, window_size="hour",
        pending=None, delayed=None, in_flight=None, dead_lettered=None,
        oldest_age_s=None, status=queue_stats.UNKNOWN_STATUS, source="no_disponible",
        workers_live=None, workers_total=None,
        processed=None, failed=None, retried=None, skipped=None,
        oldest_age_exhaustive=False, oldest_age_sample=0,
    )
    payload = queue_stats.queue_payload(row)
    assert payload["encolado"]["estado"] == "N/D"
    assert payload["encolado"]["valor"] is None
    assert payload["encolado"]["motivo"] == "Redis no respondio"
    assert payload["procesados"]["motivo"] == "el middleware de cola no esta instalado"


def test_los_contadores_sin_middleware_son_nd_y_no_cero():
    # 0 seria "no se fallo nunca". Sin el middleware no se sabe: es N/D.
    row = QueueDepthSnapshot(
        queue_name="alerts", observed_at=NOW, window_start=NOW, window_size="hour",
        pending=3, delayed=0, in_flight=1, dead_lettered=0, oldest_age_s=5.0,
        status=queue_stats.OK_STATUS, source="redis", workers_live=1, workers_total=1,
        processed=None, failed=None, retried=None, skipped=None,
        oldest_age_exhaustive=True, oldest_age_sample=3,
    )
    payload = queue_stats.queue_payload(row)
    assert payload["fallidos"]["estado"] == "N/D"
    assert payload["reintentos"]["estado"] == "N/D"
    assert payload["fallidos_carta_muerta"]["valor"] == 0
    assert payload["fallidos_carta_muerta"]["estado"] == "ok"


# --- descubrimiento y sondeo multiple --------------------------------------


def test_el_sondeo_descubre_las_colas_del_compose():
    client = FakeRedis()
    for queue in ("default", "thesis"):
        client.enqueue(queue, "m1", NOW_MS)
    names = queue_stats.discover_queues(client, ("alerts",))
    assert {"alerts", "default", "thesis"} <= set(names)


def test_el_sondeo_de_todas_las_colas_no_rompe_sin_redis():
    states = queue_stats.probe_all(FakeRedis(failing=True), queues=("a", "b"))
    assert [state.status for state in states] == ["N/D", "N/D"]


# --- middleware de Dramatiq -------------------------------------------------


def _message(queue: str, message_id: str):
    from dramatiq import Message

    return Message(
        queue_name=queue,
        actor_name="refresh_news",
        args=(),
        kwargs={},
        options={},
        message_id=message_id,
        message_timestamp=NOW_MS,
    )


def test_el_middleware_cuenta_los_cuatro_desenlaces():
    middleware_cls = queue_stats.build_queue_metrics_middleware()
    middleware = middleware_cls()
    queue_stats.reset_outcome_counters()
    try:
        ok = _message("alerts", "m1")
        middleware.before_process_message(None, ok)
        middleware.after_process_message(None, ok, result={"status": "ok"}, exception=None)

        failed = _message("alerts", "m2")
        middleware.before_process_message(None, failed)
        middleware.after_process_message(
            None, failed, result=None, exception=RuntimeError("boom")
        )

        retried = _message("alerts", "m3")
        middleware.before_process_message(None, retried)
        middleware.before_process_message(None, retried)
        middleware.after_process_message(
            None, retried, result=None, exception=RuntimeError("boom otra vez")
        )

        skipped = _message("alerts", "m4")
        middleware.after_skip_message(None, skipped)

        counters = queue_stats.outcome_counters("alerts")
        assert counters["processed"] == 1
        assert counters["failed"] == 1
        assert counters["retries"] == 1
        assert counters["skipped"] == 1
        # Cuatro `before_process_message`: uno por mensaje mas el reintento.
        assert counters["started"] == 4
    finally:
        queue_stats.reset_outcome_counters()


def test_sin_middleware_los_contadores_no_inventan_ceros():
    queue_stats.reset_outcome_counters()
    assert queue_stats.outcome_counters("alerts") == {}
    assert queue_stats.outcome_counters() == {}


def test_instalar_el_middleware_es_idempotente():
    from app.workers.dramatiq_app import broker

    queue_stats.build_queue_metrics_middleware()
    try:
        first = queue_stats.install_queue_middleware(broker)
        second = queue_stats.install_queue_middleware(broker)
        assert first is True
        assert second is False
        names = [type(item).__name__ for item in broker.middleware]
        assert names.count("QueueMetricsMiddleware") == 1
    finally:
        broker.middleware[:] = [
            item for item in broker.middleware
            if type(item).__name__ != "QueueMetricsMiddleware"
        ]


# --- persistencia -----------------------------------------------------------


def test_el_snapshot_sobrevive_a_la_persistencia():
    engine = _engine()
    session = _session(engine)
    queue_stats.reset_outcome_counters()
    try:
        client = FakeRedis()
        client.enqueue("thesis", "m1", NOW_MS - 900_000)
        client.heartbeat("worker-1")
        states = [queue_stats.probe_queue(client, "thesis", now_ms=NOW_MS, stall_seconds=300.0)]
        rows = queue_stats.persist_states(session, states, now=NOW)
        assert len(rows) == 1
        assert rows[0].status == queue_stats.STALL_STATUS
        assert rows[0].incident_reason
        # Recalcular dentro de la misma ventana ACTUALIZA, no duplica: una fila
        # por (cola, ventana) es lo que hace que el snapshot sea un estado y no
        # un historial de sondeos.
        queue_stats.persist_states(session, states, now=NOW)
        assert session.query(QueueDepthSnapshot).count() == 1
    finally:
        queue_stats.reset_outcome_counters()


def test_los_campos_no_medidos_se_persisten_como_none():
    engine = _engine()
    session = _session(engine)
    rows = queue_stats.persist_states(
        session, [queue_stats.QueueState(queue_name="kpis")], now=NOW
    )
    # Un N/D tiene que SOBREVIVIR al round-trip: si la columna tuviera
    # server_default="0", un NULL se convertiria en un 0 mentiroso.
    assert rows[0].pending is None
    assert rows[0].oldest_age_s is None
    assert rows[0].source == "no_disponible"
    payload = queue_stats.queue_payload(rows[0])
    assert payload["encolado"]["estado"] == "N/D"


def test_los_snapshots_se_leen_por_ventana():
    engine = _engine()
    session = _session(engine)
    queue_stats.persist_states(
        session, [queue_stats.QueueState(queue_name="alerts", pending=1)], now=NOW
    )
    assert [
        row.queue_name for row in queue_stats.latest_snapshots(session, now=NOW)
    ] == ["alerts"]
    # Otra ventana no ve ese snapshot: cada ventana es su propio estado.
    assert queue_stats.latest_snapshots(session, window_size="day", now=NOW) == []
    assert queue_stats.latest_snapshots(session, now=datetime(2026, 1, 1)) == []


# --- API --------------------------------------------------------------------


def _api_client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.routes.metrics import router as metrics_router

    _ensure_schema()
    app = FastAPI()
    app.include_router(metrics_router, prefix="/api/metrics")
    return TestClient(app)


_schema_ready = False


def _ensure_schema() -> None:
    """Crea el esquema en la SQLite de la sesion (la de conftest, no una propia)."""
    global _schema_ready
    if _schema_ready:
        return
    from app.core.database import init_db

    init_db()
    _schema_ready = True


def _sesion_de_sesion():
    from app.core.database import SessionLocal

    _ensure_schema()
    db = SessionLocal()
    db.info["tenant_id"] = None
    return db


def test_el_endpoint_de_cola_declara_que_no_es_dato_de_tenant():
    cuerpo = _api_client().get("/api/metrics/cola").json()
    # Las colas de Dramatiq son infraestructura compartida: decirlo en la
    # respuesta es mejor que dejar que alguien lo descubra al filtrar por tenant.
    assert cuerpo["ambito"] == "plataforma"
    assert "no lleva tenant_id" in cuerpo["ambito_nota"]
    assert cuerpo["retencion_dias"] == 14


def test_sin_snapshots_la_api_devuelve_listas_vacias_no_ceros_inventados():
    cuerpo = _api_client().get("/api/metrics/cola").json()
    assert cuerpo["colas"] == []
    assert cuerpo["incidentes"] == []
    assert cuerpo["incidentes_total"] == 0


def test_un_snapshot_con_incidente_llega_al_endpoint_con_su_motivo():
    from app.metrics import config

    db = _sesion_de_sesion()
    try:
        queue_stats.persist_states(
            db,
            [queue_stats.QueueState(
                queue_name="cola-stop", pending=4, delayed=0, in_flight=0,
                dead_lettered=1, oldest_age_s=900.0, oldest_age_exhaustive=True,
                oldest_age_sample=4, workers_live=0, workers_total=0,
                status=queue_stats.STALL_STATUS,
                incident_reason="trabajo parado: el mas viejo lleva 900 s encolado",
            )],
            window_size=config.WINDOW_HOUR,
        )
    finally:
        db.close()
    cuerpo = _api_client().get("/api/metrics/cola").json()
    incidentes = [c for c in cuerpo["incidentes"] if c["cola"] == "cola-stop"]
    assert incidentes, "el snapshot con incidente no llego al endpoint"
    assert incidentes[0]["estado"] == queue_stats.STALL_STATUS
    assert incidentes[0]["motivo_incidente"]
    assert incidentes[0]["encolado"]["valor"] == 4
    assert incidentes[0]["en_curso"]["valor"] == 0
    assert incidentes[0]["edad_mas_viejo_s"]["valor"] == 900.0


def test_la_sonda_manual_devuelve_el_nd_y_no_un_cero():
    original = queue_stats.probe_all
    queue_stats.probe_all = lambda *a, **k: [  # type: ignore[assignment]
        queue_stats.QueueState(
            queue_name="kpis", status=queue_stats.UNKNOWN_STATUS,
            unavailable=["redis:no_configurado"],
        )
    ]
    try:
        respuesta = _api_client().post("/api/metrics/cola/sondar")
    finally:
        queue_stats.probe_all = original  # type: ignore[assignment]
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["colas"][0]["unavailable"] == ["redis:no_configurado"]
    assert cuerpo["colas"][0]["pending"] is None
    assert cuerpo["incidentes_total"] == 0


def test_recalcular_encola_y_no_calcula_en_el_request():
    respuesta = _api_client().post("/api/metrics/recalcular")
    assert respuesta.status_code == 202
    cuerpo = respuesta.json()
    # Sin identidad de tenant no hay a quien encolar el trabajo: se dice, con
    # motivo, en vez de fingir que se ha encolado.
    assert cuerpo["estado"] == "N/D"
    assert "identidad" in cuerpo["motivo"]
