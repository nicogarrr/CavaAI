"""Market indices endpoint: real index/futures/crypto quotes via Yahoo Finance.

Fuente: Yahoo Finance chart API (gratuita, sin key) con User-Agent de navegador.
Cache en memoria de 60s para no golpear Yahoo en cada carga de la home.
"""
from __future__ import annotations

from typing import Literal

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models import Company, MarketPrice
from app.services.provenance import SourceKind, coverage_for_age, provenance

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

_cache: dict = {"at": 0.0, "items": [], "fetched_at": None}
_CACHE_TTL = 60.0
_FETCH_MAX_WORKERS = 5
_cache_lock = threading.RLock()


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


_QUOTE_CACHE_TTL = 60.0
_QUOTE_CACHE_MAX = 512
_quote_cache: dict[str, dict] = {}
_quote_cache_lock = threading.RLock()

_YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart"


def _fetch_yahoo_quote(client: httpx.Client, symbol: str) -> dict | None:
    """Cotización puntual via Yahoo chart API con shape Finnhub {c,d,dp,h,l,o,pc}.

    Yahoo es la única fuente gratuita sin key que cubre mercados no-US
    (IBEX .MC, .PA, .DE...); Finnhub free no los sirve. Devuelve None ante
    cualquier dato incompleto en lugar de inventar valores.
    """
    try:
        resp = client.get(
            f"{_YAHOO_CHART_URL}/{symbol}",
            params={"range": "5d", "interval": "1d"},
            timeout=15,
        )
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None
    try:
        result = resp.json()["chart"]["result"][0]
        quote = result["indicators"]["quote"][0]
        closes = [value for value in quote["close"] if value is not None]
        if not closes or closes[-1] <= 0:
            return None
        meta = result.get("meta") or {}
        last = float(closes[-1])
        previous = (
            float(closes[-2])
            if len(closes) >= 2
            else float(meta.get("chartPreviousClose") or last)
        )
        opens = [value for value in (quote.get("open") or []) if value is not None]
        highs = [value for value in (quote.get("high") or []) if value is not None]
        lows = [value for value in (quote.get("low") or []) if value is not None]
        change = last - previous
        return {
            "c": last,
            "d": change,
            "dp": (change / previous * 100) if previous else 0.0,
            "h": float(highs[-1]) if highs else last,
            "l": float(lows[-1]) if lows else last,
            "o": float(opens[-1]) if opens else last,
            "pc": previous,
        }
    except (KeyError, IndexError, TypeError, ValueError):
        return None


@router.get("/quote/{symbol}")
def market_quote(symbol: str) -> dict:
    """Cotización puntual con shape Finnhub, fuente Yahoo Finance chart API.

    Revive el fallback del frontend (getStockQuote) para tickers que Finnhub
    free no cubre (IBEX .MC y otros mercados). Caché en memoria de 60s por
    símbolo para no golpear Yahoo en bucles (watchlist, overview).
    """
    normalized = symbol.strip().upper()
    if not normalized:
        raise HTTPException(status_code=404, detail="Sin cotización disponible")
    now = time.monotonic()
    with _quote_cache_lock:
        cached = _quote_cache.get(normalized)
        if cached and now - cached["at"] < _QUOTE_CACHE_TTL:
            return cached["data"]
    headers = dict(_HEADERS)
    with httpx.Client(headers=headers) as client:
        data = _fetch_yahoo_quote(client, normalized)
    if not data:
        raise HTTPException(status_code=404, detail="Sin cotización disponible")
    with _quote_cache_lock:
        if len(_quote_cache) >= _QUOTE_CACHE_MAX:
            _quote_cache.clear()
        _quote_cache[normalized] = {"at": now, "data": data}
    return data


_CANDLES_CACHE_TTL = 900.0
_CANDLES_CACHE_MAX = 128
_candles_cache: dict[tuple, dict] = {}
_candles_cache_lock = threading.RLock()

_YAHOO_INTERVAL_BY_RESOLUTION = {"D": "1d", "W": "1wk", "M": "1mo", "60": "60m"}


def _fetch_yahoo_candles(
    client: httpx.Client, symbol: str, from_ts: int, to_ts: int, interval: str
) -> dict | None:
    """Velas históricas vía Yahoo chart API con shape Finnhub {s,c,t,o,h,l,v}.

    Finnhub free no sirve /stock/candle para mercados no-US; Yahoo sí. Las
    posiciones con close null (huecos) se descartan en TODOS los arrays para
    mantener la alineación por índice que espera el frontend.
    """
    try:
        resp = client.get(
            f"{_YAHOO_CHART_URL}/{symbol}",
            params={"period1": from_ts, "period2": to_ts, "interval": interval},
            timeout=20,
        )
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None
    try:
        result = resp.json()["chart"]["result"][0]
        timestamps = result.get("timestamp") or []
        quote = result["indicators"]["quote"][0]
        closes_raw = quote["close"]
        opens_raw = quote.get("open") or []
        highs_raw = quote.get("high") or []
        lows_raw = quote.get("low") or []
        volumes_raw = quote.get("volume") or []
        t: list[int] = []
        c: list[float] = []
        o: list[float] = []
        h: list[float] = []
        l: list[float] = []
        v: list[float] = []
        for index, close in enumerate(closes_raw):
            if close is None:
                continue
            close = float(close)
            t.append(int(timestamps[index]))
            c.append(close)
            o.append(float(opens_raw[index]) if opens_raw[index] is not None else close)
            h.append(float(highs_raw[index]) if highs_raw[index] is not None else close)
            l.append(float(lows_raw[index]) if lows_raw[index] is not None else close)
            v.append(float(volumes_raw[index]) if volumes_raw and volumes_raw[index] is not None else 0.0)
        if not c:
            return None
        return {"s": "ok", "c": c, "t": t, "o": o, "h": h, "l": l, "v": v}
    except (KeyError, IndexError, TypeError, ValueError):
        return None


@router.get("/candles/{symbol}")
def market_candles(
    symbol: str,
    from_ts: int = Query(alias="from", ge=0),
    to_ts: int = Query(alias="to", ge=1),
    resolution: Literal["D", "W", "M", "60"] = "D",
) -> dict:
    """Velas históricas con shape Finnhub, fuente Yahoo Finance chart API.

    Fallback del frontend (getCandles) para mercados que Finnhub free no
    cubre (IBEX .MC y otros). Caché en memoria de 15 min por
    (símbolo, resolución, rango horario).
    """
    normalized = symbol.strip().upper()
    if not normalized or to_ts <= from_ts:
        raise HTTPException(status_code=404, detail="Sin velas disponibles")
    interval = _YAHOO_INTERVAL_BY_RESOLUTION[resolution]
    # El rango exacto cambia en cada petición; se agrupa por hora de fin para
    # que el gráfico de la ficha (ventana de 1 año) comparta caché.
    cache_key = (normalized, interval, from_ts // 86400, to_ts // 3600)
    now = time.monotonic()
    with _candles_cache_lock:
        cached = _candles_cache.get(cache_key)
        if cached and now - cached["at"] < _CANDLES_CACHE_TTL:
            return cached["data"]
    headers = dict(_HEADERS)
    with httpx.Client(headers=headers) as client:
        data = _fetch_yahoo_candles(client, normalized, from_ts, to_ts, interval)
    if not data:
        raise HTTPException(status_code=404, detail="Sin velas disponibles")
    with _candles_cache_lock:
        if len(_candles_cache) >= _CANDLES_CACHE_MAX:
            _candles_cache.clear()
        _candles_cache[cache_key] = {"at": now, "data": data}
    return data


@router.get("/indices")
def market_indices() -> dict:
    settings = get_settings()
    now = time.monotonic()
    with _cache_lock:
        cache_hit = now - _cache["at"] < _CACHE_TTL and bool(_cache["items"])
        items = list(_cache["items"]) if cache_hit else []
        fetched_at = _cache["fetched_at"] if cache_hit else None
    if not cache_hit:
        items = []
        headers = dict(_HEADERS)
        # Yahoo respeta mejor el UA completo; el proxy/rate limit es suave a 5 tickers.
        with httpx.Client(headers=headers) as client:
            with ThreadPoolExecutor(
                max_workers=min(_FETCH_MAX_WORKERS, len(_INDEXES))
            ) as pool:
                futures = {
                    pool.submit(_fetch_index, client, index["symbol"]): index
                    for index in _INDEXES
                }
                for future, index in futures.items():
                    quote = future.result()
                    if quote:
                        items.append({**index, **quote})
        fetched_at = datetime.now(UTC)
        with _cache_lock:
            _cache["at"] = time.monotonic()
            _cache["items"] = list(items)
            _cache["fetched_at"] = fetched_at
    return {
        "source": "yahoo_finance",
        "as_of": time.time(),
        "indices": items,
        "provenance": provenance(
            "Yahoo Finance",
            SourceKind.UNOFFICIAL,
            source_url="https://finance.yahoo.com/",
            fetched_at=fetched_at,
            coverage=coverage_for_age(
                "yahoo_finance", fetched_at, partial=0 < len(items) < len(_INDEXES), empty=not items
            ),
            note="Fuente no oficial (agregador); no usar como precio autoritativo.",
        ),
    }


@router.get("/movers")
def market_movers(
    db: Session = Depends(get_db),
    limit: int = Query(default=10, ge=1, le=25),
) -> dict:
    """Gainers/losers/más activas calculados desde market_prices local.

    Diseño frío-seguro: sin filas no hay KeyError ni 500 — se devuelve
    universo vacío y la UI lo muestra como estado honesto. El cambio se
    calcula entre los dos últimos cierres de cada compañía (nunca se asume
    caché caliente ni fechas globales).
    """
    ranked = (
        select(
            MarketPrice.company_id,
            MarketPrice.date,
            MarketPrice.close,
            MarketPrice.volume,
            func.row_number()
            .over(
                partition_by=MarketPrice.company_id,
                order_by=desc(MarketPrice.date),
            )
            .label("rn"),
        )
        .order_by(MarketPrice.company_id, desc(MarketPrice.date))
        .cte("ranked")
    )
    rows = list(
        db.execute(
            select(
                ranked.c.company_id,
                ranked.c.date,
                ranked.c.close,
                ranked.c.volume,
                Company.ticker,
                Company.name,
                Company.sector,
                Company.currency,
            )
            .join(Company, Company.id == ranked.c.company_id)
            .where(ranked.c.rn <= 2)
        ).all()
    )
    latest: dict[int, dict] = {}
    previous: dict[int, dict] = {}
    for company_id, day, close, volume, ticker, name, sector, currency in rows:
        entry = {
            "ticker": ticker,
            "name": name,
            "sector": sector,
            "currency": currency,
            "price": float(close or 0),
            "volume": int(volume or 0),
            "date": day.isoformat() if day else None,
        }
        if company_id not in latest:
            latest[company_id] = entry
        elif company_id not in previous:
            previous[company_id] = entry
    movers = []
    for company_id, last in latest.items():
        prev = previous.get(company_id)
        base = float(prev["price"]) if prev else 0.0
        # Sin cierre anterior no hay cambio medible: None (la UI muestra "—"),
        # nunca un 0.0% que aparenta un dato que no existe.
        change_pct = round((last["price"] - base) / base * 100, 2) if base else None
        movers.append({**last, "change_pct": change_pct})
    as_of = max(
        (entry["date"] for entry in latest.values() if entry["date"]),
        default=None,
    )
    with_change = [m for m in movers if m["change_pct"] is not None]
    gainers = sorted(with_change, key=lambda m: m["change_pct"], reverse=True)[:limit]
    losers = sorted(with_change, key=lambda m: m["change_pct"])[:limit]
    most_active = sorted(movers, key=lambda m: m["volume"], reverse=True)[:limit]
    return {
        "as_of": as_of,
        "universe": len(movers),
        "gainers": gainers,
        "losers": losers,
        "most_active": most_active,
    }