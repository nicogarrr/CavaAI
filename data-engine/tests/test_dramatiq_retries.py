"""Regression tests: transient worker errors must reach Dramatiq for retry.

Bug-hunt finding: every actor swallowed all exceptions into a `_failure`
payload, which made `max_retries`/`min_backoff` dead — transient errors
(DB blips, Redis drops, upstream 5xx/429) never retried.
"""

import httpx
import pytest
import redis.exceptions as redis_exc
from sqlalchemy import exc as sa_exc

from app.workers.dramatiq_app import _handle_actor_error, _is_transient


def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://upstream.example/api")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError("boom", request=request, response=response)


@pytest.mark.parametrize(
    "exc",
    [
        ConnectionError("db down"),
        TimeoutError("slow"),
        sa_exc.OperationalError("SELECT 1", {}, Exception("reset")),
        sa_exc.TimeoutError(),
        redis_exc.ConnectionError("redis gone"),
        redis_exc.TimeoutError("redis slow"),
        httpx.ConnectTimeout("upstream slow"),
        httpx.ReadTimeout("upstream slow"),
        httpx.RemoteProtocolError("dropped"),
        _http_status_error(429),
        _http_status_error(503),
    ],
)
def test_transient_errors_are_classified_as_retryable(exc):
    assert _is_transient(exc) is True


@pytest.mark.parametrize(
    "exc",
    [
        ValueError("Document 42 was not found"),
        KeyError("missing_field"),
        TypeError("bad payload"),
        _http_status_error(400),
        _http_status_error(404),
    ],
)
def test_permanent_errors_are_not_retried(exc):
    assert _is_transient(exc) is False


def test_handler_reraises_transient_so_dramatiq_retries():
    with pytest.raises(ConnectionError):
        _handle_actor_error("some_actor", ConnectionError("db down"), ticker="MSFT")


def test_handler_returns_structured_payload_for_permanent_errors():
    result = _handle_actor_error("some_actor", ValueError("not found"), ticker="MSFT")
    assert result["status"] == "error"
    assert result["actor"] == "some_actor"
    assert result["error"]["type"] == "ValueError"
    assert result["error"]["context"] == {"ticker": "MSFT"}


def _sec_error(status_code: int) -> httpx.HTTPStatusError:
    url = "https://www.sec.gov/Archives/edgar/data/320193/x.htm"
    request = httpx.Request("GET", url)
    response = httpx.Response(status_code, request=request)
    # Mensaje con el formato real de httpx: incluye la URL (la heuristica de
    # clasificacion mira "sec.gov" en el texto de la excepcion).
    kind = "Client" if status_code < 500 else "Server"
    return httpx.HTTPStatusError(f"{kind} error '{status_code}' for url '{url}'", request=request, response=response)


def _reset_sec_breaker():
    import app.workers.dramatiq_app as workers

    workers._sec_429_streak.clear()
    workers._sec_429_open_until = 0.0


def test_sec_403_from_oci_blocked_ip_is_permanent():
    """F359: 403 de la SEC evidencia bloqueo de IP (OCI): permanente, sin
    reintento. Reintentarlo enveneno la cola default (5276 mensajes)."""
    assert _is_transient(_sec_error(403)) is False
    wrapped = RuntimeError(f"SEC fetch failed: {_sec_error(403)}")
    assert _is_transient(wrapped) is False


def test_sec_429_retries_bounded_until_circuit_breaker_trips():
    """F359: 429 de la SEC es rate limit potencialmente temporal: se reintenta
    de forma acotada; una racha en ventana abre el circuit breaker por origen
    y pasa a permanente durante el cooldown (auto-recupera despues)."""
    import app.workers.dramatiq_app as workers

    _reset_sec_breaker()
    # Racha por debajo del limite: sigue siendo transitorio.
    for _ in range(workers._SEC_429_STREAK_LIMIT - 1):
        assert _is_transient(_sec_error(429)) is True
    # La que alcanza el limite abre el breaker: permanente.
    assert _is_transient(_sec_error(429)) is False
    # Abierto, los siguientes tambien son permanentes sin tocar el contador.
    assert _is_transient(_sec_error(429)) is False
    # Tras el cooldown vuelve a permitir reintento.
    workers._sec_429_open_until = 0.0
    assert _is_transient(_sec_error(429)) is True
    _reset_sec_breaker()


def test_generic_429_and_5xx_stay_retryable():
    """El tallo de la SEC no cubre otros proveedores: un 429/5xx generico
    sigue siendo transitorio y Dramatiq lo reintenta."""
    assert _is_transient(_http_status_error(429)) is True
    assert _is_transient(_http_status_error(503)) is True
