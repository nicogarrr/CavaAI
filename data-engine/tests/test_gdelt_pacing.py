"""GDELT pacing + cola prices: la tormenta de 429 no debe volver a saturar la cola."""

import asyncio
import time

import httpx
import pytest

from app.services.connectors.gdelt import GDELTClient


class _StubClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[float] = []

    async def get(self, url, params=None):
        self.calls.append(time.monotonic())
        return self.responses.pop(0)


def _resp(status: int, payload: dict | None = None, retry_after: str | None = None):
    headers = {"Retry-After": retry_after} if retry_after else {}
    return httpx.Response(status, json=payload or {"articles": []}, headers=headers, request=httpx.Request("GET", "https://api.gdeltproject.org/api/v2/doc/doc"))


def test_throttle_enforces_min_interval():
    stub = _StubClient([_resp(200), _resp(200), _resp(200)])
    client = GDELTClient(client=stub, min_interval=0.05)
    GDELTClient._next_allowed_at = 0.0  # estado limpio para el test

    async def run():
        for _ in range(3):
            await client.news_search("apple")

    asyncio.run(run())
    gaps = [b - a for a, b in zip(stub.calls, stub.calls[1:])]
    assert all(gap >= 0.045 for gap in gaps), gaps


def test_429_retry_after_then_success():
    stub = _StubClient([_resp(429, retry_after="0"), _resp(200, {"articles": [{"url": "u"}]})])
    client = GDELTClient(client=stub, min_interval=0, max_429_retries=2)
    GDELTClient._next_allowed_at = 0.0
    out = asyncio.run(client.news_search("apple"))
    assert out == {"articles": [{"url": "u"}]}
    assert len(stub.calls) == 2


def test_429_exhaustion_raises():
    stub = _StubClient([_resp(429, retry_after="0"), _resp(429, retry_after="0"), _resp(429, retry_after="0")])
    client = GDELTClient(client=stub, min_interval=0, max_429_retries=2)
    GDELTClient._next_allowed_at = 0.0
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(client.news_search("apple"))
    assert len(stub.calls) == 3


def test_retry_after_default_when_header_missing():
    assert GDELTClient._retry_after_seconds(_resp(429)) == GDELTClient.DEFAULT_RETRY_AFTER
    assert GDELTClient._retry_after_seconds(_resp(429, retry_after="999")) == GDELTClient.MAX_RETRY_AFTER
    assert GDELTClient._retry_after_seconds(_resp(429, retry_after="abc")) == GDELTClient.DEFAULT_RETRY_AFTER


def test_price_actors_on_prices_queue():
    from app.workers import dramatiq_app

    assert dramatiq_app.refresh_market_pipeline.queue_name == "prices"
    assert dramatiq_app.refresh_portfolio_prices_intraday.queue_name == "prices"
    # los demás actores siguen en default
    assert dramatiq_app.refresh_news.queue_name == "default"
