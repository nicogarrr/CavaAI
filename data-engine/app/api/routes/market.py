"""Market indices endpoint: real index/futures/crypto quotes via Yahoo Finance.

Fuente: Yahoo Finance chart API (gratuita, sin key) con User-Agent de navegador.
Cache en memoria de 60s para no golpear Yahoo en cada carga de la home.
"""
from __future__ import annotations

import time

import httpx
from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter()

_INDEXES = [
    {"symbol": "^GSPC", "name": "S&P 500"},
    {"symbol": "^IXIC", "name": "Nasdaq Composite"},
    {"symbol": "BTC-USD", "name": "Bitcoin"},
    {"symbol": "GC=F", "name": "Oro"},
    {"symbol": "SI=F", "name": "Plata"},
]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

_cache: dict = {"at": 0.0, "items": []}
_CACHE_TTL = 60.0


def _fetch_index(client: httpx.Client, symbol: str) -> dict | None:
    try:
        resp = client.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            params={"range": "5d", "interval": "1d"},
            timeout=15,
        )
        if resp.status_code != 200:
            return None
        payload = resp.json()
        result = payload["chart"]["result"][0]
        closes = [
            value
            for value in result["indicators"]["quote"][0]["close"]
            if value is not None
        ]
        if len(closes) < 2:
            return None
        last, previous = closes[-1], closes[-2]
        change = last - previous
        change_percent = (change / previous) * 100 if previous else 0.0
        return {
            "symbol": symbol,
            "price": round(float(last), 2),
            "change": round(float(change), 2),
            "changePercent": round(float(change_percent), 2),
        }
    except (httpx.HTTPError, KeyError, IndexError, ValueError):
        return None


@router.get("/indices")
def market_indices() -> dict:
    settings = get_settings()
    now = time.monotonic()
    if now - _cache["at"] < _CACHE_TTL and _cache["items"]:
        items = _cache["items"]
    else:
        items = []
        headers = dict(_HEADERS)
        # Yahoo respeta mejor el UA completo; el proxy/rate limit es suave a 5 tickers.
        with httpx.Client(headers=headers) as client:
            for index in _INDEXES:
                quote = _fetch_index(client, index["symbol"])
                if quote:
                    items.append({**index, **quote})
        _cache["at"] = now
        _cache["items"] = items
    return {
        "source": "yahoo_finance",
        "as_of": time.time(),
        "indices": items,
    }