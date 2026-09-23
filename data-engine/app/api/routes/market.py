"""Market indices endpoint: real index/futures/crypto quotes via Yahoo Finance.

Fuente: Yahoo Finance chart API (gratuita, sin key) con User-Agent de navegador.
Cache en memoria de 60s para no golpear Yahoo en cada carga de la home.
"""
from __future__ import annotations

import time
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Depends, Query
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
        fetched_at = _cache["fetched_at"]
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
        fetched_at = datetime.now(UTC)
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
            )
            .join(Company, Company.id == ranked.c.company_id)
            .where(ranked.c.rn <= 2)
        ).all()
    )
    latest: dict[int, dict] = {}
    previous: dict[int, dict] = {}
    for company_id, day, close, volume, ticker, name, sector in rows:
        entry = {
            "ticker": ticker,
            "name": name,
            "sector": sector,
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
        change_pct = ((last["price"] - base) / base * 100) if base else 0.0
        movers.append({**last, "change_pct": round(change_pct, 2)})
    as_of = max(
        (entry["date"] for entry in latest.values() if entry["date"]),
        default=None,
    )
    gainers = sorted(movers, key=lambda m: m["change_pct"], reverse=True)[:limit]
    losers = sorted(movers, key=lambda m: m["change_pct"])[:limit]
    most_active = sorted(movers, key=lambda m: m["volume"], reverse=True)[:limit]
    return {
        "as_of": as_of,
        "universe": len(movers),
        "gainers": gainers,
        "losers": losers,
        "most_active": most_active,
    }