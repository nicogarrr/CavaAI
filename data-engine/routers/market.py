"""Market data, quotes, news, and strategy API routes."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Body, HTTPException, Query

from modules.fmp import (
    fetch_biggest_gainers,
    fetch_biggest_losers,
    fetch_fmp_articles,
    fetch_general_news,
    fetch_most_actives,
    fetch_stock_peers,
    fetch_stock_screener,
)
from modules.garp import run_garp_strategy
from modules.yfinance_utils import (
    fetch_yf_batch_quotes,
    fetch_yf_dividends,
    fetch_yf_insider_trading,
    fetch_yf_news,
    fetch_yf_single_quote,
    fetch_yf_stock_info,
)

router = APIRouter(tags=["market"])


def _raise_if_error(data):
    if isinstance(data, dict) and "error" in data:
        raise HTTPException(status_code=500, detail=data["error"])


@router.get("/market-movers/gainers")
async def get_biggest_gainers():
    data = fetch_biggest_gainers()
    _raise_if_error(data)
    return {"gainers": data}


@router.get("/market-movers/losers")
async def get_biggest_losers():
    data = fetch_biggest_losers()
    _raise_if_error(data)
    return {"losers": data}


@router.get("/market-movers/active")
async def get_most_actives():
    data = fetch_most_actives()
    _raise_if_error(data)
    return {"actives": data}


@router.get("/screener")
async def get_screener_stocks(
    marketCapMoreThan: Optional[int] = Query(None, description="Market Cap greater than"),
    sector: Optional[str] = Query(None, description="Sector filter"),
    limit: int = Query(20, description="Limit results"),
):
    data = fetch_stock_screener(marketCapMoreThan, sector, limit)
    _raise_if_error(data)
    return {"screener": data}


@router.get("/news/fmp-articles")
async def get_fmp_articles_endpoint(page: int = Query(0, description="Page number"), limit: int = Query(20)):
    try:
        data = fetch_fmp_articles(page, limit)
        if isinstance(data, dict) and "error" in data:
            return []
        return data
    except Exception:
        return []


@router.get("/news/general")
async def get_general_news_endpoint(page: int = 0, limit: int = 20):
    return fetch_general_news(page, limit)


@router.get("/dividends/{symbol}")
async def get_dividends(symbol: str, limit: int = Query(50, description="Number of dividend records")):
    symbol = symbol.upper()
    dividends = fetch_yf_dividends(symbol, limit)
    if dividends:
        try:
            info = fetch_yf_stock_info(symbol)
            if info and info.get("dividendYield"):
                dividends[0]["yield"] = round(info["dividendYield"] * 100, 2)
        except Exception:
            pass
    return dividends


@router.get("/stock-peers/{symbol}")
async def get_stock_peers_endpoint(symbol: str, with_prices: bool = Query(False, description="Include current prices")):
    symbol = symbol.upper()
    data = fetch_stock_peers(symbol)
    if not isinstance(data, list) or not data:
        return []

    if isinstance(data[0], str):
        peer_symbols = data[:8]
    else:
        peer_symbols = [p.get("symbol", p) if isinstance(p, dict) else p for p in data[:8]]

    if with_prices and peer_symbols:
        quotes = fetch_yf_batch_quotes(peer_symbols)
        result = []
        for sym in peer_symbols:
            sym_upper = sym.upper() if isinstance(sym, str) else sym
            quote = quotes.get(sym_upper, {})
            result.append({
                "symbol": sym_upper,
                "companyName": quote.get("companyName", sym_upper),
                "price": quote.get("price", 0),
                "mktCap": quote.get("marketCap", 0),
                "change": quote.get("change", 0),
                "changePercent": quote.get("changePercent", 0),
            })
        return result

    return [{"symbol": s.upper() if isinstance(s, str) else s, "companyName": s, "price": 0, "mktCap": 0} for s in peer_symbols]


@router.get("/quote/{symbol}")
async def get_stock_quote_endpoint(symbol: str):
    quote = fetch_yf_single_quote(symbol.upper())
    if quote:
        return quote
    return {"c": 0, "d": 0, "dp": 0, "h": 0, "l": 0, "o": 0, "pc": 0}


@router.post("/batch-quotes")
async def get_batch_quotes(symbols: List[str] = Body(..., description="List of stock symbols")):
    if not symbols:
        return {}
    limited_symbols = [s.upper() for s in symbols[:20]]
    return fetch_yf_batch_quotes(limited_symbols)


@router.get("/insider-trading/{symbol}")
async def get_insider_trading(symbol: str, limit: int = Query(50, description="Number of transactions to return")):
    try:
        return {"symbol": symbol.upper(), "insiderTrades": fetch_yf_insider_trading(symbol.upper(), limit)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/strategies/garp")
async def get_garp_strategy(limit: int = 10):
    try:
        data = run_garp_strategy(limit=limit)
        return {"strategy": "GARP Top 12 Months", "count": len(data), "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/company-news/{symbol}")
async def get_company_news(symbol: str, limit: int = Query(20, description="News limit")):
    try:
        return fetch_yf_news(symbol.upper(), limit)
    except Exception:
        return []


@router.get("/test")
async def test_endpoint():
    return {"status": "ok"}
