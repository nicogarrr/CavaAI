"""T1: resilience — external failures become explicit degraded states,
never fabricated data. Hermetic: mocked transports, no network."""

from datetime import datetime

import httpx
import pytest

from app.api.routes import market
from app.services.connectors import cnmv
from app.services.connectors.base import ConnectorResult


class _FailingTransport(httpx.AsyncBaseTransport):
    def __init__(self, status_code=500, body=b"server error"):
        self.status_code = status_code
        self.body = body

    async def handle_async_request(self, request):
        return httpx.Response(self.status_code, content=self.body, request=request)


class _TimeoutTransport(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request):
        raise httpx.ConnectTimeout("simulated timeout", request=request)


def test_connector_result_failed_shape():
    """The shared failure envelope: explicit error state, zero items (no filler)."""
    result = ConnectorResult.failed("cnmv", RuntimeError("boom"))
    assert result.status == "error"
    assert result.items == []
    assert result.errors == ["boom"]
    payload = result.as_dict()
    assert payload["status"] == "error"
    datetime.fromisoformat(payload["fetched_at"])


def test_partial_failure_is_explicit_not_silent():
    result = ConnectorResult(source="x", items=[], errors=["1 of 3 feeds failed"])
    assert result.status == "error"  # nothing served -> error, not fake "ok"
    from app.services.connectors.base import ConnectorItem

    result2 = ConnectorResult(source="x", items=[ConnectorItem(source="x", title="t")], errors=["1 feed failed"])
    assert result2.status == "partial"  # partial is visible, never upgraded to ok


@pytest.mark.anyio
async def test_cnmv_5xx_raises_for_honest_degradation():
    async with httpx.AsyncClient(transport=_FailingTransport(503)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await cnmv.fetch_oir_filings(days=1, client=client)


@pytest.mark.anyio
async def test_cnmv_timeout_raises_for_honest_degradation():
    async with httpx.AsyncClient(transport=_TimeoutTransport()) as client:
        with pytest.raises(httpx.ConnectTimeout):
            await cnmv.fetch_oir_filings(days=1, client=client)


def test_cnmv_corrupt_html_is_parse_error_not_empty_success():
    with pytest.raises(cnmv.CNMVParseError):
        cnmv.parse_oir_results("<html><body>redesign</body></html>")


def test_cnmv_rejects_absurd_day_windows():
    with pytest.raises(ValueError):
        import asyncio

        asyncio.run(cnmv.fetch_oir_filings(days=365))


def test_market_total_failure_is_unavailable_not_fabricated(monkeypatch):
    """When every quote fails, the endpoint says unavailable with zero items."""
    monkeypatch.setattr(market, "_cache", {"at": 0.0, "items": [], "fetched_at": None})
    monkeypatch.setattr(market, "_fetch_index", lambda client, symbol: None)

    class _Client:
        def __init__(self, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(market.httpx, "Client", _Client)
    result = market.market_indices()
    assert result["indices"] == []
    assert result["provenance"]["coverage"] == "unavailable"


def test_market_cached_fetch_time_never_fabricated(monkeypatch):
    """Serving from cache keeps the original fetch time (P1a), even minutes later."""
    monkeypatch.setattr(market, "_cache", {"at": 0.0, "items": [], "fetched_at": None})
    monkeypatch.setattr(market, "_fetch_index", lambda client, symbol: {"price": 1.0, "change_pct": 0.0})

    class _Client:
        def __init__(self, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(market.httpx, "Client", _Client)
    first = market.market_indices()["provenance"]["fetched_at"]
    second = market.market_indices()["provenance"]["fetched_at"]
    assert first == second
    datetime.fromisoformat(first)
