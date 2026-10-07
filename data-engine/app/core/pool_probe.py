"""Sonda de pool de BD: localiza que codigo retiene conexiones.

El 7-oct (18:33-18:39) el pool del backend (5+10) se agoto con 15 conexiones
"sacadas" que nadie devolvia, y el log de peticiones solo sale al terminar, asi
que las colgadas no dejaban rastro. Esta sonda registra, por cada conexion
sacada, cuando y desde que frames de app/ se saco; si el numero de conexiones
fuera del pool llega al umbral, vuelca (con limite de frecuencia) las mas
antiguas. Solo escribe nombres de fichero/funcion/linea del propio codigo y
edades: nunca consultas, parametros ni datos.
"""

from __future__ import annotations

import logging
import threading
import time
import traceback

from sqlalchemy import event

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_OUT: dict[int, tuple[float, str]] = {}
_LAST_DUMP = 0.0
_INSTALLED = False


def _frames() -> str:
    keep = [
        f"{f.filename.split('/app/')[-1]}:{f.lineno}:{f.name}"
        for f in traceback.extract_stack(limit=40)
        if "/app/app/" in f.filename and "pool_probe" not in f.filename
    ]
    return " < ".join(reversed(keep[-4:]))


def outstanding() -> list[tuple[float, str]]:
    now = time.monotonic()
    with _LOCK:
        return sorted(((now - t, where) for t, where in _OUT.values()), reverse=True)


def install(engine, *, threshold: int = 10, min_interval_s: float = 30.0) -> None:
    """Engancha eventos checkout/checkin al pool del engine (idempotente)."""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    @event.listens_for(engine, "checkout")
    def _on_checkout(dbapi_conn, _record, _proxy):  # noqa: ANN001
        global _LAST_DUMP
        where = _frames()
        with _LOCK:
            _OUT[id(_record)] = (time.monotonic(), where)
            count = len(_OUT)
            due = count >= threshold and time.monotonic() - _LAST_DUMP >= min_interval_s
            if due:
                _LAST_DUMP = time.monotonic()
        if due:
            top = outstanding()[:5]
            logger.warning(
                "db pool pressure: %d connections out; oldest: %s",
                count,
                " | ".join(f"{age:.0f}s {where or '?'}" for age, where in top),
            )

    @event.listens_for(engine, "checkin")
    def _on_checkin(_dbapi_conn, record):  # noqa: ANN001
        # Clave = connection_record, no la conexion DBAPI: al invalidar, SQLAlchemy
        # entrega dbapi_conn=None y la entrada quedaria como fantasma.
        with _LOCK:
            _OUT.pop(id(record), None)


SLOW_REQUEST_SECONDS = 5.0


class SlowRequestMiddleware:
    """ASGI puro: avisa de las peticiones que tardan mas de `threshold_s`.

    Registra metodo, ruta (sin query string), status, duracion y conexiones del
    pool sacadas al terminar. Nunca cuerpo, cabeceras ni parametros.
    """

    def __init__(self, app, threshold_s: float = SLOW_REQUEST_SECONDS, pool_out=None) -> None:  # noqa: ANN001
        self.app = app
        self.threshold_s = threshold_s
        self._pool_out = pool_out

    def _checked_out(self) -> int | str:
        try:
            if self._pool_out is not None:
                return self._pool_out()
            from app.core.database import engine

            return engine.pool.checkedout()
        except Exception:  # noqa: BLE001 - observabilidad: jamas rompe la peticion
            return "?"

    async def __call__(self, scope, receive, send) -> None:  # noqa: ANN001
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        started = time.monotonic()
        state = {"status": 0}

        async def _send(message):  # noqa: ANN001
            if message.get("type") == "http.response.start":
                state["status"] = int(message.get("status") or 0)
            await send(message)

        try:
            await self.app(scope, receive, _send)
        finally:
            elapsed = time.monotonic() - started
            if elapsed >= self.threshold_s:
                logger.warning(
                    "slow request: %s %s status=%s %.1fs pool_checkedout=%s",
                    scope.get("method", "?"),
                    scope.get("path", "?"),
                    state["status"] or "-",
                    elapsed,
                    self._checked_out(),
                )
