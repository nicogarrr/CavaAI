"""Profundidad de cola y salud de los workers (#E5, metrica 2).

De donde salen los numeros. El broker es `RedisBroker`, y su script
`dispatch.lua` documenta el layout de claves, que es el unico contrato fiable:

    dramatiq:{cola}            LIST  ids de mensajes encolados, sin coger
    dramatiq:{cola}.msgs       HASH  id -> cuerpo (permanece hasta el ack)
    dramatiq:{cola}.DQ         LIST  ids de mensajes con retardo
    dramatiq:{cola}.XQ         ZSET  ids de cartas muertas (reintentos agotados)
    dramatiq:__heartbeats__    ZSET  worker_id -> ultimo latido, en ms

De ahi sale el "en curso" sin sondear la BD de negocio: un mensaje sigue en el
hash `.msgs` hasta que el worker hace ack, asi que
`en_curso = HLEN(.msgs) - LLEN(cola)`. Es una RESTA, no un ABS, y por eso es
O(1) en vez de un SCAN.

La edad del trabajo mas viejo sale de `message_timestamp` del cuerpo del mensaje.
Decodificar toda una cola grande en cada sonda es O(n) sobre JSON, asi que se
decodifica como mucho `BACKEND_METRICS_QUEUE_AGE_SAMPLE` cuerpos y, cuando no se
ha visto el hash entero, el resultado se declara como estimacion
(`oldest_age_exhaustive: false`). Preferimos un numero con su limites declarados
a un numero exacto que cuesta un segundo por sonda.

**Worker parado es un INCIDENTE, no un statistic.** Si hay trabajo encolado mas
viejo que el umbral y no hay nada en curso, la cola no esta "profunda": esta
parada. Eso se reporta como `status="incidente"` con su razon, que es lo unico
que hace que alguien mire el panel.

**Los contadores de resultado (procesado / fallido / saltado / reintentos) vienen
de un middleware de Dramatiq**, no de sondear Redis: el resultado de un mensaje
que ya se consumio no existe en ninguna clave. Se-living counters en el proceso
del worker; ver `QueueMetricsMiddleware` e `install_queue_middleware()`.

**WORKERS_ENABLED**: este modulo no lee ese flag ni lo cambia. Solo sondea
cuando se le pide, y los tests (que lo ponen a false) siguen sin arrancar workers.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.metrics import config
from app.models.metrics import QueueDepthSnapshot

logger = logging.getLogger(__name__)

NAMESPACE = "dramatiq"
STALL_STATUS = "incidente"
DEGRADED_STATUS = "degradado"
OK_STATUS = "ok"
UNKNOWN_STATUS = "N/D"

HEARTBEATS_KEY = f"{NAMESPACE}:__heartbeats__"


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def queue_key(queue: str) -> str:
    return f"{NAMESPACE}:{queue}"


@dataclass
class QueueState:
    """Estado de UNA cola en un instante. `None` en un campo = no medido."""

    queue_name: str
    pending: int | None = None
    delayed: int | None = None
    in_flight: int | None = None
    dead_lettered: int | None = None
    oldest_age_s: float | None = None
    oldest_age_exhaustive: bool = False
    oldest_age_sample: int = 0
    # Vivos = workers con latido dentro del timeout de Dramatiq (60 s por
    # defecto). `None` = la clave de latidos no se pudo leer, que no es lo mismo
    # que "no hay workers".
    workers_live: int | None = None
    workers_total: int | None = None
    newest_heartbeat_age_s: float | None = None
    status: str = UNKNOWN_STATUS
    incident_reason: str | None = None
    measured_fields: list[str] = field(default_factory=list)
    unavailable: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def _redis_client(client: Any = None):
    """Cliente Redis corto. `None` si no hay URL; nunca lanza."""
    if client is not None:
        return client
    from app.core.config import get_settings

    url = getattr(get_settings(), "redis_url", "") or ""
    if not url:
        return None
    import redis as _redis

    return _redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)


def _len(client: Any, key: str) -> int:
    return int(client.llen(key) or 0)


def _hlen(client: Any, key: str) -> int:
    return int(client.hlen(key) or 0)


def _zcard(client: Any, key: str) -> int:
    return int(client.zcard(key) or 0)


def _sample_values(client: Any, key: str, limit: int) -> tuple[list[str], bool]:
    """Hasta `limit` valores del hash y si se ha visto entero.

    HSCAN con COUNT 100 es O(limit) en vez de O(n): con una cola de 50.000
    mensajes, leerlos todos en cada sonda seria un segundo de CPU por cola y por
    invocation del scheduler, y el numero que sale seria el mismo.
    """
    total = _hlen(client, key)
    if total <= 0:
        return [], True
    if total <= limit:
        return [str(value) for value in (client.hvals(key) or [])], True
    collected: list[str] = []
    for _message_id, raw in client.hscan_iter(key, count=100):
        collected.append(raw.decode() if isinstance(raw, bytes) else str(raw))
        if len(collected) >= limit:
            break
    return collected, False


def oldest_message_age_s(
    client: Any, queue: str, now_ms: int, limit: int
) -> tuple[float | None, bool, int]:
    """(edad en segundos del mensaje mas viejo, muestreo completo, muestras)."""
    key = f"{queue_key(queue)}.msgs"
    raw_values, exhaustive = _sample_values(client, key, limit)
    oldest_ms: int | None = None
    seen = 0
    for raw in raw_values:
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            continue
        stamp = payload.get("message_timestamp")
        if not isinstance(stamp, (int, float)):
            continue
        seen += 1
        if oldest_ms is None or stamp < oldest_ms:
            oldest_ms = int(stamp)
    if oldest_ms is None:
        return None, exhaustive, seen
    return max(0.0, (now_ms - oldest_ms) / 1000.0), exhaustive, seen


def worker_heartbeats(client: Any, now_ms: int, timeout_s: float) -> tuple[int | None, int | None, float | None]:
    """(vivos, totales, antiguedad del latido mas reciente) en segundos.

    `vivos` son los workers cuyo ultimo latido es mas reciente que el timeout
    (60 s por defecto en `RedisBroker`); ese es el criterio que usa el propio
    Dramatiq para reencolar el trabajo de un worker muerto, asi que es el mismo
    que declara aqui.
    """
    try:
        total = _zcard(client, HEARTBEATS_KEY)
        cutoff = now_ms - int(timeout_s * 1000)
        live = int(client.zcount(HEARTBEATS_KEY, cutoff, "+inf"))
    except Exception as exc:  # noqa: BLE001 — la sonda nunca rompe el panel
        logger.debug("latidos ilegibles: %s", type(exc).__name__)
        return None, None, None
    newest = None
    try:
        row = client.zrange(HEARTBEATS_KEY, -1, -1, withscores=True)
        if row:
            newest = float(row[0][1])
    except Exception:  # noqa: BLE001
        newest = None
    age_s = None if newest is None else max(0.0, (now_ms - newest) / 1000.0)
    return live, total, age_s


def discover_queues(client: Any, known: tuple[str, ...] | None = None) -> list[str]:
    """Colas conocidas del compose + las que aparezcan en Redis.

    El SCAN esta acotado a 40 iteraciones: descubrir colas no es una funcion de
    la que dependa la correccion de la metrica (la lista del compose es la
    fuente), asi que no se deja que un Redis lleno la convierta en un barrido.
    """
    found = set(known if known is not None else config.known_queues())
    try:
        for index, key in enumerate(client.scan_iter(match=f"{NAMESPACE}:*", count=200)):
            if index >= 40:
                break
            name = str(key.decode() if isinstance(key, bytes) else key)[len(NAMESPACE) + 1:]
            if not name or name.startswith("__") or name.endswith((".msgs", ".XQ", ".acks")):
                continue
            base = name.split(".")[0]
            if base:
                found.add(base)
    except Exception as exc:  # noqa: BLE001 — sin Redis, la lista del compose basta
        logger.debug("descubrimiento de colas no disponible: %s", type(exc).__name__)
    return sorted(found)


def probe_queue(
    client: Any,
    queue: str,
    *,
    now_ms: int | None = None,
    sample_limit: int | None = None,
    stall_seconds: float | None = None,
    dead_worker_seconds: float | None = None,
) -> QueueState:
    """Estado de una cola. Nunca lanza: un Redis caido sale como N/D con motivo."""
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    sample_limit = sample_limit or config.queue_age_sample_limit()
    stall_seconds = stall_seconds if stall_seconds is not None else config.queue_stall_seconds()
    dead_worker_s = (
        dead_worker_seconds
        if dead_worker_seconds is not None
        else config.queue_dead_worker_seconds()
    )
    state = QueueState(queue_name=queue)
    base = queue_key(queue)
    try:
        pending = _len(client, base)
        pending_delayed = _len(client, f"{base}.DQ")
        stored = _hlen(client, f"{base}.msgs")
        dead = _zcard(client, f"{base}.XQ")
    except Exception as exc:  # noqa: BLE001 — Redis caido es N/D, no 0
        state.unavailable.append(f"redis:{type(exc).__name__}")
        state.incident_reason = None
        return state
    state.pending = pending
    state.delayed = pending_delayed
    state.dead_lettered = dead
    state.in_flight = max(0, stored - pending)
    state.measured_fields = ["pending", "delayed", "in_flight", "dead_lettered"]
    try:
        age, exhaustive, seen = oldest_message_age_s(client, queue, now_ms, sample_limit)
        state.oldest_age_s = age
        state.oldest_age_exhaustive = exhaustive
        state.oldest_age_sample = seen
        if age is not None:
            state.measured_fields.append("oldest_age_s")
    except Exception as exc:  # noqa: BLE001
        state.unavailable.append(f"oldest_age:{type(exc).__name__}")
    live, total, heartbeat_age = worker_heartbeats(client, now_ms, dead_worker_s)
    state.workers_live = live
    state.workers_total = total
    state.newest_heartbeat_age_s = heartbeat_age
    _classify(state, stall_seconds, dead_worker_s, heartbeat_age)
    return state


def _classify(
    state: QueueState, stall_seconds: float, dead_worker_s: float, heartbeat_age_s: float | None
) -> None:
    """ok | degradado | incidente, con su razon. La razon va SIEMPRE con el estado."""
    if state.pending is None:
        state.status = UNKNOWN_STATUS
        state.incident_reason = None
        return
    if state.pending > 0 and state.in_flight == 0:
        if state.oldest_age_s is None:
            state.status = DEGRADED_STATUS
            state.incident_reason = (
                f"{state.pending} encolados y nada en curso, sin edad medible: "
                "no se puede afirmar que la cola este parada"
            )
            return
        if state.oldest_age_s > stall_seconds:
            state.status = STALL_STATUS
            state.incident_reason = (
                f"trabajo parado: el mas viejo lleva {state.oldest_age_s:.0f} s encolado "
                f"(umbral {stall_seconds:.0f} s) y hay 0 mensajes en curso"
            )
            return
        state.status = OK_STATUS
        return
    if state.pending > 0 and (state.in_flight or 0) > 0 and state.oldest_age_s is not None:
        if state.oldest_age_s > stall_seconds * 4:
            state.status = DEGRADED_STATUS
            state.incident_reason = (
                f"la cola no avanza: {state.oldest_age_s:.0f} s sin vaciarse con "
                f"{state.in_flight} mensajes en curso"
            )
            return
    if heartbeat_age_s is not None and heartbeat_age_s > dead_worker_s * 10:
        state.status = DEGRADED_STATUS
        state.incident_reason = (
            f"ningun worker da latidos desde hace {heartbeat_age_s:.0f} s"
        )
        return
    state.status = OK_STATUS


def probe_all(
    client: Any = None,
    *,
    queues: tuple[str, ...] | None = None,
    now_ms: int | None = None,
) -> list[QueueState]:
    """Sondea todas las colas. Sin Redis devuelve N/D por cola, no ceros."""
    client = _redis_client(client)
    if client is None:
        return [
            QueueState(
                queue_name=queue,
                status=UNKNOWN_STATUS,
                unavailable=["redis:no_configurado"],
            )
            for queue in (queues or config.known_queues())
        ]
    return [
        probe_queue(client, queue, now_ms=now_ms)
        for queue in discover_queues(client, queues)
    ]


# --- contadores en proceso (middleware de Dramatiq) --------------------------

_outcome_lock = threading.Lock()
_outcomes: dict[str, dict[str, int]] = {}


def _bump(queue: str, key: str, amount: int = 1) -> None:
    with _outcome_lock:
        bucket = _outcomes.setdefault(queue, {})
        bucket[key] = bucket.get(key, 0) + amount


def outcome_counters(queue: str | None = None) -> dict[str, int]:
    """Contadores EN PROCESO. `{}` si el middleware no esta instalado (N/D)."""
    with _outcome_lock:
        if queue is not None:
            return dict(_outcomes.get(queue, {}))
        merged: dict[str, int] = {}
        for bucket in _outcomes.values():
            for key, value in bucket.items():
                merged[key] = merged.get(key, 0) + value
        return merged


def reset_outcome_counters() -> None:
    with _outcome_lock:
        _outcomes.clear()


def build_queue_metrics_middleware():
    """Clase de middleware de Dramatiq. Import perezoso: dramatiq es opcional.

    Devuelve la clase, no la instancia: llamarla a nivel de modulo registrarla
    en el broker global como efecto secundario, que es justo lo que hace
    `install_queue_middleware()`.
    """
    import dramatiq

    class QueueMetricsMiddleware(dramatiq.Middleware):
        """Cuenta resultados por cola con los hooks del propio Dramatiq.

        `before_process_message` + `after_process_message` + `after_nack` +
        `after_skip_message` cubren los cuatro desenlaces: lo procesado con
        exito, lo que se reencola tras fallar (reintento), lo que se manda a
        carta muerta y lo que se salta por limite de reintentos. Ninguno
        necesita tocar la BD de negocio.
        """

        def __init__(self) -> None:
            self._attempts: dict[str, int] = {}

        @property
        def actor_name(self) -> str:
            return "QueueMetricsMiddleware"

        def before_process_message(self, broker, message) -> None:
            queue = str(getattr(message, "queue_name", "") or "default")
            key = str(getattr(message, "message_id", "") or "")
            if key:
                self._attempts[key] = self._attempts.get(key, 0) + 1
            _bump(queue, "started")

        def after_process_message(self, broker, message, *, result=None, exception=None) -> None:
            queue = str(getattr(message, "queue_name", "") or "default")
            key = str(getattr(message, "message_id", "") or "")
            attempts = self._attempts.pop(key, 1) if key else 1
            if exception is not None:
                if attempts > 1:
                    _bump(queue, "retries")
                else:
                    _bump(queue, "failed")
            else:
                _bump(queue, "processed")

        def after_nack(self, broker, message) -> None:
            _bump(str(getattr(message, "queue_name", "") or "default"), "retries")

        def after_skip_message(self, broker, message) -> None:
            _bump(str(getattr(message, "queue_name", "") or "default"), "skipped")

    return QueueMetricsMiddleware


def install_queue_middleware(broker: Any = None) -> bool:
    """Registra el middleware UNA vez en el broker. Idempotente.

    Punto de integracion (se anade en `app/workers/dramatiq_app.py`, fichero
    congelado mientras otros agentes trabajan sobre el):

        from app.metrics.queue import install_queue_middleware
        install_queue_middleware()

    Sin esa linea, la profundidad y la edad del trabajo mas viejo siguen siendo
    correctas (se leen de Redis, sin este modulo) y lo UNICO que falta son los
    contadores de resultado, que salen como N/D en vez de 0.
    """
    middleware_cls = build_queue_metrics_middleware()
    if broker is None:
        from app.workers.dramatiq_app import broker as default_broker

        broker = default_broker
    existing = getattr(broker, "middleware", None) or []
    if any(type(item).__name__ == middleware_cls.__name__ for item in existing):
        return False
    broker.add_middleware(middleware_cls())
    return True


def persist_states(
    db: Session,
    states: list[QueueState],
    *,
    window_size: str = "hour",
    now: datetime | None = None,
) -> list[QueueDepthSnapshot]:
    """Guarda un snapshot por cola. `None` en un campo se guarda como None (N/D)."""
    from app.metrics import stats

    moment = now or utcnow_naive()
    start = stats.window_start(moment, window_size)
    snapshots: list[QueueDepthSnapshot] = []
    for state in states:
        existing = db.scalar(
            select(QueueDepthSnapshot)
            .where(
                QueueDepthSnapshot.queue_name == state.queue_name,
                QueueDepthSnapshot.window_start == start,
                QueueDepthSnapshot.window_size == window_size,
            )
            .order_by(QueueDepthSnapshot.observed_at.desc())
            .limit(1)
        )
        per_queue = outcome_counters(state.queue_name)
        row = existing or QueueDepthSnapshot(
            queue_name=state.queue_name,
            window_start=start,
            window_size=window_size,
        )
        row.observed_at = moment
        row.pending = state.pending
        row.delayed = state.delayed
        row.in_flight = state.in_flight
        row.dead_lettered = state.dead_lettered
        row.oldest_age_s = state.oldest_age_s
        row.oldest_age_exhaustive = state.oldest_age_exhaustive
        row.oldest_age_sample = state.oldest_age_sample
        row.workers_live = state.workers_live
        row.workers_total = state.workers_total
        row.newest_heartbeat_age_s = state.newest_heartbeat_age_s
        row.processed = per_queue.get("processed")
        row.failed = per_queue.get("failed")
        row.skipped = per_queue.get("skipped")
        row.retried = per_queue.get("retries")
        row.status = state.status
        row.incident_reason = state.incident_reason
        # `no_disponible` si la sonda fallo o si los contadores basicos no se
        # midieron. Un estado con `pending=None` no viene de un Redis que
        # respondio, asi que no puede etiquetarse como si viniera.
        row.source = (
            "no_disponible" if state.unavailable or state.pending is None else "redis"
        )
        db.add(row)
        snapshots.append(row)
    db.commit()
    return snapshots


def latest_snapshots(
    db: Session, *, window_size: str = "hour", now: datetime | None = None
) -> list[QueueDepthSnapshot]:
    """Ultimo snapshot de cada cola dentro de la ventana que contiene `now`."""
    from app.metrics import stats

    start = stats.window_start(now or utcnow_naive(), window_size)
    rows = list(
        db.scalars(
            select(QueueDepthSnapshot)
            .where(
                QueueDepthSnapshot.window_start == start,
                QueueDepthSnapshot.window_size == window_size,
            )
            .order_by(QueueDepthSnapshot.queue_name, QueueDepthSnapshot.observed_at.desc())
        ).all()
    )
    seen: dict[str, QueueDepthSnapshot] = {}
    for row in rows:
        seen.setdefault(row.queue_name, row)
    return [seen[name] for name in sorted(seen)]


def queue_payload(row: QueueDepthSnapshot) -> dict:
    """Payload de una cola con N/D explicito donde no hubo medicion."""
    unavailable = row.source == "no_disponible"

    def field_or_nd(value: Any, motivo: str) -> dict:
        if unavailable:
            return {"estado": "N/D", "valor": None, "motivo": motivo}
        if value is None:
            return {"estado": "N/D", "valor": None, "motivo": "sin dato en el snapshot"}
        return {"estado": "ok", "valor": value, "motivo": None}

    return {
        "cola": row.queue_name,
        "observado_en": row.observed_at.isoformat() if row.observed_at else None,
        "ventana": {"inicio": row.window_start.isoformat(), "tamano": row.window_size},
        "estado": row.status,
        "motivo_incidente": row.incident_reason,
        "encolado": field_or_nd(row.pending, "Redis no respondio"),
        "retrasado": field_or_nd(row.delayed, "Redis no respondio"),
        "en_curso": field_or_nd(row.in_flight, "Redis no respondio"),
        "fallidos_carta_muerta": field_or_nd(row.dead_lettered, "Redis no respondio"),
        "edad_mas_viejo_s": field_or_nd(row.oldest_age_s, "sin mensaje encolado al que medir"),
        "edad_mas_viejo_exhaustiva": bool(row.oldest_age_exhaustive),
        "edad_mas_viejo_muestras": int(row.oldest_age_sample or 0),
        "workers_vivos": field_or_nd(row.workers_live, "sin clave de latidos"),
        "workers_totales": field_or_nd(row.workers_total, "sin clave de latidos"),
        "procesados": field_or_nd(row.processed, "el middleware de cola no esta instalado"),
        "fallidos": field_or_nd(row.failed, "el middleware de cola no esta instalado"),
        "reintentos": field_or_nd(row.retried, "el middleware de cola no esta instalado"),
        "saltados": field_or_nd(row.skipped, "el middleware de cola no esta instalado"),
    }