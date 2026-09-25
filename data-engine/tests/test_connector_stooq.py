"""Hermetic tests: Stooq daily CSV fallback. No network."""

from datetime import date

import httpx
import pytest

from app.services.connectors.stooq import StooqClient


@pytest.mark.asyncio
async def test_stooq_parses_daily_csv_with_source_and_date():
    def handler(request):
        assert request.url.params["s"] == "aapl.us"
        return httpx.Response(200, text="Date,Open,High,Low,Close,Volume\n2026-09-24,100.1,103,99,102.5,1234\n")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rows = await StooqClient(client).daily_prices("AAPL.US", start=date(2026, 9, 1), end=date(2026, 9, 25))
    assert rows[0]["date"] == date(2026, 9, 24)
    assert str(rows[0]["close"]) == "102.5"
    assert rows[0]["volume"] == 1234
    assert rows[0]["source"] == "stooq"


@pytest.mark.asyncio
async def test_stooq_rejects_challenge_and_bad_prices():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, text="<!DOCTYPE html><html>verify browser</html>"))) as client:
        with pytest.raises(RuntimeError, match="HTML"):
            await StooqClient(client).daily_prices("aapl.us", start=date(2026, 9, 1), end=date(2026, 9, 25))
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, text="Date,Open,High,Low,Close,Volume\n2026-09-24,100,103,99,-1,10\n"))) as client:
        with pytest.raises(RuntimeError, match="invalid"):
            await StooqClient(client).daily_prices("aapl.us", start=date(2026, 9, 1), end=date(2026, 9, 25))
