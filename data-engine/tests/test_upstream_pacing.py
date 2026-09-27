"""Pacing de los proveedores con clave: 429 se reintenta, el mapa CIK se cachea.

Dos costes que se pagan en cuota del proveedor, no en CPU:

1. FMP, Finnhub y FRED hacen `raise_for_status()` y nada mas. Su plan FREE es
   de 60 (Finnhub), 120 (FRED) y 250 (FMP) llamadas/min, y el consumo normal ya
   lo ronda: el refresco de precios hace fan-out sobre el universo entero del
   tenant con 6 conexiones simultaneas. Un 429 era un fallo definitivo, el
   llamante lo registraba como "proveedor no disponible" y los precios de esa
   corrida se perdian sin reintento. Ahora se reintenta 429 y 5xx con backoff
   respetando Retry-After, y solo esos: un 401/403/404 es de configuracion o de
   entitlement y reintentar solo gasta cuota.

2. `company_tickers.json` son ~2 MB y se descargaba una vez POR TICKER, porque
   `resolve_ciks` la llama en bucle sobre la watchlist. Una watchlist de 40
   emisores son 40 descargas de 2 MB a sec.gov en una pasada, y la weekly
   insider scan multiplica eso por 200. Es exactamente el patron que hace que
   la SEC limite o banee la IP de salida por fair-access.
"""

from __future__ import annotations

import asyncio
import inspect

import httpx
import pytest

from app.services.connectors.base import (
    UpstreamRateLimited,
    get_with_retry,
    retry_after_seconds,
)
from app.services.connectors.finnhub import FinnhubClient
from app.services.connectors.fmp import FMPClient


class _Response:
    def __init__(self, status: int, headers: dict | None = None, payload: dict | None = None):
        self.status_code = status
        self.headers = headers or {}
        self._payload = payload if payload is not None else {"ok": True}

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"status {self.status_code}",
                request=httpx.Request("GET", "https://x.test"),
                response=httpx.Response(self.status_code),
            )


def _client(monkeypatch) -> FMPClient:
    monkeypatch.setattr(
        "app.services.connectors.fmp.get_settings",
        lambda: type("S", (), {"fmp_api_key": "test-key"})(),
    )
    return FMPClient()


# --------------------------------------------------------------------------
# 1. Reintentos con presupuesto y Retry-After
# --------------------------------------------------------------------------


def test_429_retry_after_beyond_cap_postpones_without_inline_retry():
    calls = {"n": 0}

    async def fetch():
        calls["n"] += 1
        return _Response(429, {"retry-after": "3600"})

    with pytest.raises(UpstreamRateLimited, match="pospuesto sin reintento"):
        asyncio.run(get_with_retry(fetch))
    # Sin reintento inline: una sola llamada, no se espera ni se quema cuota.
    assert calls["n"] == 1


def test_429_retry_after_within_cap_still_retries_inline():
    calls = {"n": 0}

    async def fetch():
        calls["n"] += 1
        return _Response(429 if calls["n"] == 1 else 200, {"retry-after": "1"})

    result = asyncio.run(get_with_retry(fetch))
    assert result.status_code == 200
    assert calls["n"] == 2


def test_retry_after_seconds_truncates_but_never_exceeds_cap():
    response = _Response(429, {"retry-after": "3600"})
    assert retry_after_seconds(response) == 120.0


def test_429_is_retried_and_can_succeed():
    calls = {"n": 0}

    async def fetch():
        calls["n"] += 1
        return _Response(429 if calls["n"] < 3 else 200, {"retry-after": "0"})

    result = asyncio.run(get_with_retry(fetch))
    assert result.status_code == 200
    assert calls["n"] == 3


def test_5xx_is_retried():
    calls = {"n": 0}

    async def fetch():
        calls["n"] += 1
        return _Response(503 if calls["n"] == 1 else 200)

    assert asyncio.run(get_with_retry(fetch, base_seconds=0)).status_code == 200
    assert calls["n"] == 2


def test_4xx_other_than_429_is_not_retried():
    """Un 403 es de entitlement: reintentar solo gasta cuota."""
    calls = {"n": 0}

    async def fetch():
        calls["n"] += 1
        return _Response(403)

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(get_with_retry(fetch, base_seconds=0))
    assert calls["n"] == 1


def test_429_exhausting_retries_raises_a_named_error():
    async def fetch():
        return _Response(429, {"retry-after": "0"})

    with pytest.raises(UpstreamRateLimited):
        asyncio.run(get_with_retry(fetch, max_retries=2, base_seconds=0))
    with pytest.raises(UpstreamRateLimited):
        asyncio.run(get_with_retry(fetch, max_retries=0))


def test_timeouts_are_retried():
    calls = {"n": 0}

    async def fetch():
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectTimeout("boom")
        return _Response(200)

    assert asyncio.run(get_with_retry(fetch, base_seconds=0)).status_code == 200


def test_retry_after_is_honoured_and_capped():
    assert retry_after_seconds(_Response(429, {"retry-after": "7"})) == 7.0
    assert retry_after_seconds(_Response(429, {"retry-after": "9999"}), cap=30.0) == 30.0
    assert retry_after_seconds(_Response(429, {})) == 0.0
    assert retry_after_seconds(_Response(429, {"retry-after": "luego"})) == 0.0


def test_retry_budget_is_bounded():
    """Con presupuesto 0 no hay esperas: el numero de intentos es acotado."""
    calls = {"n": 0}

    async def fetch():
        calls["n"] += 1
        return _Response(429, {"retry-after": "0"})

    with pytest.raises(UpstreamRateLimited):
        asyncio.run(get_with_retry(fetch, max_retries=2, base_seconds=0))
    assert calls["n"] == 3  # intento inicial + 2 reintentos


@pytest.mark.parametrize("client_cls", [FMPClient, FinnhubClient])
def test_keyed_clients_use_the_shared_retry(client_cls):
    source = inspect.getsource(client_cls._get)
    assert "get_with_retry" in source, (
        f"{client_cls.__name__} sigue haciendo raise_for_status() sin reintentar: "
        "un 429 del proveedor se convertia en cobertura perdida"
    )


# --------------------------------------------------------------------------
# 2. El mapa ticker -> CIK se cachea
# --------------------------------------------------------------------------


def test_cik_map_is_downloaded_once(monkeypatch):
    from app.services import insider_service

    monkeypatch.setattr(insider_service, "_CIK_MAP_CACHE", None, raising=False)
    monkeypatch.setattr(insider_service, "_CIK_MAP_LOADED_AT", 0.0, raising=False)

    calls = {"n": 0}

    class _Client:
        def get(self, url, headers=None):
            calls["n"] += 1
            return _Response(
                200,
                payload={
                    "1": {"ticker": "AAPL", "cik_str": 320193},
                    "2": {"ticker": "msft", "cik_str": 789019},
                },
            )

    client = _Client()
    first = insider_service._cik_for_ticker("AAPL", client=client)
    second = insider_service._cik_for_ticker("MSFT", client=client)
    third = insider_service._cik_for_ticker("AAPL", client=client)

    assert first == "0000320193"
    assert second == "0000789019"
    assert third == "0000320193"
    assert calls["n"] == 1, (
        f"company_tickers.json se descargo {calls['n']} veces; con 40 tickers "
        "en la watchlist son 80 MB contra sec.gov en una pasada"
    )


def test_cik_lookup_is_case_and_whitespace_insensitive(monkeypatch):
    from app.services import insider_service

    monkeypatch.setattr(insider_service, "_CIK_MAP_CACHE", None, raising=False)
    monkeypatch.setattr(insider_service, "_CIK_MAP_LOADED_AT", 0.0, raising=False)

    class _Client:
        def get(self, url, headers=None):
            return _Response(200, payload={"1": {"ticker": "AAPL", "cik_str": 320193}})

    assert insider_service._cik_for_ticker("  aapl ", client=_Client()) == "0000320193"


def test_unknown_ticker_returns_none(monkeypatch):
    from app.services import insider_service

    monkeypatch.setattr(insider_service, "_CIK_MAP_CACHE", None, raising=False)
    monkeypatch.setattr(insider_service, "_CIK_MAP_LOADED_AT", 0.0, raising=False)

    class _Client:
        def get(self, url, headers=None):
            return _Response(200, payload={"1": {"ticker": "AAPL", "cik_str": 320193}})

    assert insider_service._cik_for_ticker("ZZZZ", client=_Client()) is None
