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
