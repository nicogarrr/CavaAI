"""OpenFIGI sync: rate limit, cache TTL, retry solo 429/5xx. Todo mockeado."""

import httpx

from app.services.connectors import openfigi as mod
from app.services.connectors.openfigi import (
    OpenFIGICache,
    OpenFIGIConnector,
    OpenFIGIRateLimiter,
    is_retryable_status,
)


def test_retryable_only_429_and_5xx():
    assert is_retryable_status(429)
    assert is_retryable_status(500)
    assert is_retryable_status(503)
    assert not is_retryable_status(400)
    assert not is_retryable_status(404)
    assert not is_retryable_status(403)


def test_rate_limiter_blocks_after_quota():
    limiter = OpenFIGIRateLimiter(requests_per_minute=2)
    assert limiter.wait_seconds() == 0.0
    limiter.record()
    limiter.record()
    assert limiter.wait_seconds() > 0


def test_cache_ttl_expiry(monkeypatch):
    cache = OpenFIGICache(ttl_seconds=60)
    now = [1000.0]
    monkeypatch.setattr(mod.time, "monotonic", lambda: now[0])
    cache.set("ID_ISIN", "US0378331005", {"status": "matched"})
    assert cache.get("ID_ISIN", "US0378331005") == {"status": "matched"}
    now[0] += 61.0
    assert cache.get("ID_ISIN", "US0378331005") is None


def _client(handler, api_key=None):
    transport = httpx.MockTransport(handler)
    raw = httpx.Client(transport=transport)
    return OpenFIGIConnector(api_key=api_key, requests_per_minute=1000, client=raw)


def test_sync_connector_caches_and_sends_key_header():
    calls = []

    def handler(request):
        calls.append(dict(request.headers))
        assert request.url.path == "/v3/mapping"
        return httpx.Response(200, json=[{"data": [{"figi": "BBG1", "ticker": "AAPL"}]}])

    connector = _client(handler, api_key="KEY123")
    first = connector.map_identifier("US0378331005")
    second = connector.map_identifier("us0378331005")  # cache: sin red
    assert first["status"] == "matched"
    assert second["status"] == "matched"
    assert len(calls) == 1
    assert calls[0].get("x-openfigi-apikey") == "KEY123"


def test_sync_connector_retries_429_then_succeeds(monkeypatch):
    monkeypatch.setattr(mod.time, "sleep", lambda _: None)
    attempts = []

    def handler(request):
        attempts.append(1)
        if len(attempts) == 1:
            return httpx.Response(429, json={"error": "throttled"})
        return httpx.Response(200, json=[{"data": [{"figi": "BBG1"}]}])

    result = _client(handler).map_identifier("US0378331005")
    assert result["status"] == "matched"
    assert len(attempts) == 2


def test_sync_connector_never_retries_4xx():
    attempts = []

    def handler(request):
        attempts.append(1)
        return httpx.Response(400, json={"error": "bad"})

    result = _client(handler).map_identifier("US0378331005")
    assert result["status"] == "error"
    assert len(attempts) == 1


def test_sync_connector_invalid_inputs():
    connector = _client(lambda _: httpx.Response(200, json=[{}]))
    try:
        connector.map_identifier("   ")
        raise AssertionError("debio fallar")
    except ValueError:
        pass
    try:
        connector.map_identifier("US0378331005", id_type="ID_TICKER")
        raise AssertionError("debio fallar")
    except ValueError:
        pass
