"""Hermetic tests: OpenFIGI v3 mapping without key. No network."""

import httpx
import pytest

from app.services.connectors.openfigi import OpenFIGIClient


@pytest.mark.asyncio
async def test_openfigi_preserves_ambiguous_venue_matches():
    def handler(request):
        assert request.url.path == "/v3/mapping"
        assert request.content == b'[{"idType":"ID_ISIN","idValue":"US0378331005"}]'
        return httpx.Response(200, json=[{"data": [
            {"figi": "BBG1", "ticker": "AAPL", "exchCode": "US"},
            {"figi": "BBG2", "ticker": "AAPL", "exchCode": "UA"},
        ]}])
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await OpenFIGIClient(client).map_identifier("us0378331005")
    assert result["status"] == "ambiguous"
    assert len(result["matches"]) == 2
    assert result["source_url"] == OpenFIGIClient.base_url


@pytest.mark.asyncio
async def test_openfigi_empty_and_invalid():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[{"warning": "No identifiers found."}]))) as client:
        result = await OpenFIGIClient(client).map_identifier("UNKNOWN")
        assert result["status"] == "unavailable"
        with pytest.raises(ValueError):
            await OpenFIGIClient(client).map_identifier("US0378331005", id_type="ID_TICKER")
