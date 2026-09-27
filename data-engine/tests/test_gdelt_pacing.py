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


def test_min_interval_zero_does_not_wait():
    stub = _StubClient([_resp(200), _resp(200)])
    client = GDELTClient(client=stub, min_interval=0)
    GDELTClient._next_allowed_at = 0.0

    async def run():
        for _ in range(2):
            await client.news_search("apple")

    asyncio.run(run())
    assert stub.calls[1] - stub.calls[0] < 0.045


def test_throttle_holds_the_spacing_under_load():
    """Un overrun del evento loop no debe colapsar el intervalo siguiente.

    The reservation used to be claimed BEFORE the sleep, so a call that woke up
    late consumed its slot without waiting and the next call saw an already
    elapsed deadline and went out immediately. The spacing only held when
    nothing was slow, which is the opposite of when GDELT starts returning 429.
    """
    stub = _StubClient([_resp(200), _resp(200), _resp(200)])
    client = GDELTClient(client=stub, min_interval=0.05)
    GDELTClient._next_allowed_at = 0.0
    real_sleep = asyncio.sleep

    async def slow_sleep(delay, *args, **kwargs):
        # Simulate a loaded event loop overshooting the first wait.
        await real_sleep(delay + 0.06 if delay > 0 else 0.0)

    async def run():
        original = asyncio.sleep
        asyncio.sleep = slow_sleep
        try:
            for _ in range(3):
                await client.news_search("apple")
        finally:
            asyncio.sleep = original

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


def test_429_retry_after_beyond_max_raises_without_retry():
    stub = _StubClient([_resp(429, retry_after="3600"), _resp(200, {"articles": []})])
    client = GDELTClient(client=stub, min_interval=0, max_429_retries=2)
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(client.news_search("q"))
    assert len(stub.calls) == 1  # la ventana prohibida no se reintenta inline


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
