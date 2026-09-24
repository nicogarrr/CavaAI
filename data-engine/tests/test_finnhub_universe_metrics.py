"""Finnhub universe (/stock/symbol?exchange=US) y metric (/stock/metric):

el mandato bulk depende de que el conector pida bien estos dos endpoints
del tier gratis, asi que el contrato queda fijado con un cliente falso.
"""

import asyncio

from app.services.connectors.finnhub import FinnhubClient


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeAsyncClient:
    calls: list[tuple[str, dict]] = []
    payload = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None):
        type(self).calls.append((url, dict(params or {})))
        return _FakeResponse(type(self).payload)


def _client(monkeypatch, payload):
    _FakeAsyncClient.calls = []
    _FakeAsyncClient.payload = payload
    monkeypatch.setattr(
        "app.services.connectors.finnhub.httpx.AsyncClient", _FakeAsyncClient
    )
    client = FinnhubClient()
    monkeypatch.setattr(client.settings, "finnhub_api_key", "test-key")
    return client


def test_us_symbols_hits_free_universe_endpoint(monkeypatch):
    rows = [
        {"symbol": "AAPL", "description": "APPLE INC", "mic": "XNAS"},
        "ruido-no-dict",
        {"symbol": "RKLB", "description": "ROCKET LAB CORP", "mic": "XNAS"},
    ]
    client = _client(monkeypatch, rows)
    result = asyncio.run(client.us_symbols())
    assert [r["symbol"] for r in result] == ["AAPL", "RKLB"]
    url, params = _FakeAsyncClient.calls[0]
    assert url.endswith("/stock/symbol")
    assert params["exchange"] == "US"
    assert params["token"] == "test-key"


def test_metric_returns_inner_metric_dict(monkeypatch):
    client = _client(
        monkeypatch, {"metric": {"revenuePerShareAnnual": 1.134}, "series": {}}
    )
    result = asyncio.run(client.metric("rklb"))
    assert result == {"revenuePerShareAnnual": 1.134}
    url, params = _FakeAsyncClient.calls[0]
    assert url.endswith("/stock/metric")
    assert params == {"symbol": "RKLB", "metric": "all", "token": "test-key"}


def test_metric_rejects_payload_sin_metric(monkeypatch):
    client = _client(monkeypatch, {"series": {}})
    try:
        asyncio.run(client.metric("AAPL"))
    except RuntimeError as exc:
        assert "invalid metrics" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("debio lanzar RuntimeError")
