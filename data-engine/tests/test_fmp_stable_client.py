"""FMP client must target the /stable API.

FMP retired legacy /api/v3 endpoints for current API keys (403 "Legacy
Endpoint no longer supported"). This contract test pins the connector to
/stable URLs with ?symbol= params so a regression to legacy paths fails CI
instead of silently breaking fundamentals ingestion in production.
"""

import asyncio

import pytest

from app.core.config import get_settings
from app.services.connectors.fmp import FMPClient


class _FakeResponse:
    def __init__(self, payload=None):
        self._payload = payload if payload is not None else []

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeAsyncClient:
    calls: list[tuple[str, dict]] = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None):
        type(self).calls.append((url, dict(params or {})))
        return _FakeResponse()


@pytest.fixture
def client(monkeypatch):
    _FakeAsyncClient.calls = []
    monkeypatch.setenv("FMP_API_KEY", "test-key")
    get_settings.cache_clear()
    monkeypatch.setattr("app.services.connectors.fmp.httpx.AsyncClient", _FakeAsyncClient)
    yield FMPClient()
    get_settings.cache_clear()


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.mark.parametrize(
    "method,args,expected_path,expected_params",
    [
        ("company_profile", ("aapl",), "/profile", {"symbol": "AAPL"}),
        ("dividends", ("aapl",), "/dividends", {"symbol": "AAPL"}),
        ("splits", ("aapl",), "/splits", {"symbol": "AAPL"}),
        ("income_statement", ("aapl",), "/income-statement", {"symbol": "AAPL", "limit": 10}),
        ("balance_sheet", ("aapl",), "/balance-sheet-statement", {"symbol": "AAPL", "limit": 10}),
        ("cash_flow", ("aapl",), "/cash-flow-statement", {"symbol": "AAPL", "limit": 10}),
        ("ratios", ("aapl",), "/ratios", {"symbol": "AAPL", "limit": 10}),
        ("news", ("aapl",), "/news/stock", {"symbols": "AAPL", "limit": 25}),
    ],
)
def test_every_endpoint_uses_stable_api(client, method, args, expected_path, expected_params):
    _run(getattr(client, method)(*args))
    assert len(_FakeAsyncClient.calls) == 1
    url, params = _FakeAsyncClient.calls[0]
    assert url == f"https://financialmodelingprep.com/stable{expected_path}"
    assert "/api/v3" not in url
    assert params["apikey"] == "test-key"
    for key, value in expected_params.items():
        assert params[key] == value


def test_unconfigured_client_raises_without_http_call(monkeypatch):
    _FakeAsyncClient.calls = []
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    get_settings.cache_clear()
    monkeypatch.setattr("app.services.connectors.fmp.httpx.AsyncClient", _FakeAsyncClient)
    client = FMPClient()
    with pytest.raises(RuntimeError):
        _run(client.company_profile("AAPL"))
    assert _FakeAsyncClient.calls == []
    get_settings.cache_clear()
