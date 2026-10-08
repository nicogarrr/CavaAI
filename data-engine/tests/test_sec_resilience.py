"""F351: el cliente SEC directo aguanta 429/5xx/red, cachea y cae a EFTS.

Cero red: todo va contra httpx.MockTransport. Sin proxies ni cambio de IP.
"""

from __future__ import annotations

import asyncio
from urllib.parse import urlparse

import httpx
import pytest

from app.services.connectors import sec as sec_module
from app.services.connectors.sec import SECClient, reset_sec_client_state


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    reset_sec_client_state()

    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(sec_module.asyncio, "sleep", _no_sleep)
    yield
    reset_sec_client_state()


def _run(coro):
    return asyncio.run(coro)


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_retries_429_and_5xx_with_backoff_then_succeeds():
    calls = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "2"}, request=request)
        if calls["n"] == 2:
            return httpx.Response(503, request=request)
        return httpx.Response(200, json={"ok": True}, request=request)

    async def probe():
        async with _client(handler) as http:
            return await SECClient(client=http, requests_per_second=10)._get_json(
                "https://data.sec.gov/submissions/CIK0000000001.json"
            )

    assert _run(probe()) == {"ok": True}
    assert calls["n"] == 3


def test_retries_transport_errors_and_gives_up_after_budget():
    calls = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ConnectTimeout("boom", request=request)

    async def probe():
        async with _client(handler) as http:
            sec = SECClient(client=http, requests_per_second=10)
            with pytest.raises(httpx.ConnectTimeout):
                await sec._get("https://data.sec.gov/x.json")

    _run(probe())
    assert calls["n"] == sec_module.get_settings().sec_max_retries + 1


def test_403_is_not_retried():
    calls = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(403, request=request)

    async def probe():
        async with _client(handler) as http:
            with pytest.raises(httpx.HTTPStatusError):
                await SECClient(client=http, requests_per_second=10)._get("https://data.sec.gov/x.json")

    _run(probe())
    assert calls["n"] == 1


def test_json_responses_are_cached_across_instances():
    calls = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"n": calls["n"]}, request=request)

    async def probe():
        url = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000000002.json"
        async with _client(handler) as http:
            first = await SECClient(client=http, requests_per_second=10, use_cache=True)._get_json(url)
            second = await SECClient(client=http, requests_per_second=10, use_cache=True)._get_json(url)
            return first, second

    first, second = _run(probe())
    assert first == second == {"n": 1}
    assert calls["n"] == 1


def test_errors_are_never_cached():
    calls = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(404, request=request)
        return httpx.Response(200, json={"ok": 1}, request=request)

    async def probe():
        url = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000000003.json"
        async with _client(handler) as http:
            sec = SECClient(client=http, requests_per_second=10, use_cache=True)
            with pytest.raises(httpx.HTTPStatusError):
                await sec._get_json(url)
            return await sec._get_json(url)

    assert _run(probe()) == {"ok": 1}


def test_pacing_clock_is_shared_between_instances():
    async def probe():
        a = SECClient(requests_per_second=2)
        b = SECClient(requests_per_second=2)
        await a._throttle()
        first_slot = sec_module._next_slot_at
        await b._throttle()
        return first_slot, sec_module._next_slot_at

    first_slot, second_slot = _run(probe())
    assert second_slot - first_slot == pytest.approx(0.5, abs=0.01)


def _efts_page(rows):
    return {
        "hits": {
            "hits": [
                {
                    "_id": f"{adsh}:{doc}",
                    "_source": {
                        "adsh": adsh,
                        "form": form,
                        "file_date": filed,
                        "period_ending": period,
                        "sequence": seq,
                        "ciks": ["0000000099", "0000000004"],
                        "display_names": [
                            "DOE JANE  (CIK 0000000099)",
                            "Acme Corp  (ACME)  (CIK 0000000004)",
                        ],
                    },
                }
                for adsh, doc, form, filed, period, seq in rows
            ]
        }
    }


def test_submissions_falls_back_to_efts_when_sec_blocks_and_marks_it_partial():
    seen: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        seen.append(url)
        if urlparse(url).hostname == "efts.sec.gov":
            return httpx.Response(
                200,
                json=_efts_page(
                    [
                        ("0000000004-26-000002", "ex99.htm", "8-K", "2026-09-30", "2026-09-29", 2),
                        ("0000000004-26-000002", "acme-8k.htm", "8-K", "2026-09-30", "2026-09-29", 1),
                        ("0000000004-26-000001", "acme-10q.htm", "10-Q", "2026-08-01", "2026-06-30", 1),
                    ]
                ),
                request=request,
            )
        return httpx.Response(403, request=request)

    async def probe():
        async with _client(handler) as http:
            return await SECClient(client=http, requests_per_second=10).submissions("4")

    payload = _run(probe())
    recent = payload["filings"]["recent"]
    assert payload["_fallback"] == "efts-full-text-search"
    assert payload["name"] == "Acme Corp"  # por posicion del CIK, no display_names[0]
    assert "parcial" in payload["_fallback_note"]
    assert recent["accessionNumber"] == ["0000000004-26-000002", "0000000004-26-000001"]
    assert recent["primaryDocument"] == ["acme-8k.htm", "acme-10q.htm"]
    assert recent["form"] == ["8-K", "10-Q"]
    assert recent["reportDate"] == ["2026-09-29", "2026-06-30"]


def test_404_is_a_data_failure_and_never_goes_to_efts():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert urlparse(str(request.url)).hostname != "efts.sec.gov"
        return httpx.Response(404, request=request)

    async def probe():
        async with _client(handler) as http:
            with pytest.raises(httpx.HTTPStatusError):
                await SECClient(client=http, requests_per_second=10).submissions("5")

    _run(probe())


def test_when_efts_also_fails_the_original_error_surfaces():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, request=request)

    async def probe():
        async with _client(handler) as http:
            with pytest.raises(Exception) as info:
                await SECClient(client=http, requests_per_second=10).submissions("6")
            return info.value

    err = _run(probe())
    assert "sin mirror" in str(err)  # error original, no el de EFTS


def test_recent_filings_uses_efts_fallback_end_to_end():
    async def handler(request: httpx.Request) -> httpx.Response:
        if urlparse(str(request.url)).hostname == "efts.sec.gov":
            return httpx.Response(
                200,
                json=_efts_page([("0000000007-26-000001", "x-8k.htm", "8-K", "2026-10-01", "2026-09-30", 1)]),
                request=request,
            )
        return httpx.Response(403, request=request)

    async def probe():
        async with _client(handler) as http:
            return await SECClient(client=http, requests_per_second=10).recent_filings("7", ticker="ACME")

    result = _run(probe())
    assert len(result.items) == 1
    assert result.items[0].metadata["form"] == "8-K"
    assert result.items[0].url.endswith("/7/000000000726000001/x-8k.htm")


def test_injected_client_does_not_cache_by_default():
    """Un httpx inyectado (MockTransport) sirve fixtures distintos por caso."""
    calls = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"n": calls["n"]}, request=request)

    async def probe():
        url = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000000008.json"
        async with _client(handler) as http:
            a = await SECClient(client=http, requests_per_second=10)._get_json(url)
            b = await SECClient(client=http, requests_per_second=10)._get_json(url)
            return a, b

    assert _run(probe()) == ({"n": 1}, {"n": 2})


def test_cache_returns_copies_so_mutation_does_not_leak():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"facts": {"a": 1}}, request=request)

    async def probe():
        url = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000000009.json"
        async with _client(handler) as http:
            sec = SECClient(client=http, requests_per_second=10, use_cache=True)
            first = await sec._get_json(url)
            first["facts"]["a"] = 999
            return await sec._get_json(url)

    assert _run(probe()) == {"facts": {"a": 1}}


def test_efts_partial_coverage_is_exposed_to_consumers():
    async def handler(request: httpx.Request) -> httpx.Response:
        if urlparse(str(request.url)).hostname == "efts.sec.gov":
            return httpx.Response(
                200,
                json=_efts_page([("0000000004-26-000009", "k.htm", "10-K", "2026-02-01", "2025-12-31", 1)]),
                request=request,
            )
        return httpx.Response(403, request=request)

    async def probe():
        async with _client(handler) as http:
            sec = SECClient(client=http, requests_per_second=10)
            return await sec.recent_filings("4", ticker="ACME"), await sec.annual_report_anchors("4")

    result, anchors = _run(probe())
    assert result.metadata["source_fallback"] == "efts-full-text-search"
    assert result.metadata["partial_coverage"] is True
    assert "parcial" in result.metadata["coverage_note"]
    assert result.items[0].metadata["partial_coverage"] is True
    assert anchors == {"0000000004-26-000009": "2025-12-31"}
    assert anchors.partial is True and anchors.source == "efts-full-text-search"


def test_direct_sec_response_is_not_marked_partial():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"name": "Acme", "filings": {"recent": {"accessionNumber": ["a"], "form": ["10-K"], "reportDate": ["2025-12-31"]}}},
            request=request,
        )

    async def probe():
        async with _client(handler) as http:
            sec = SECClient(client=http, requests_per_second=10)
            return await sec.recent_filings("4"), await sec.annual_report_anchors("4")

    result, anchors = _run(probe())
    assert "partial_coverage" not in result.metadata
    assert anchors.partial is False
