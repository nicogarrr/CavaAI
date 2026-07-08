"""Fundamentals and company analysis API routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from modules.fmp import (
    fetch_analyst_estimates,
    fetch_balance_sheet,
    fetch_cash_flow,
    fetch_dcf,
    fetch_earnings_transcript,
    fetch_earnings_transcripts_list,
    fetch_enterprise_value,
    fetch_financial_growth,
    fetch_financial_scores,
    fetch_grades_consensus,
    fetch_income_statement,
    fetch_key_metrics_ttm,
    fetch_owner_earnings,
    fetch_press_releases,
    fetch_price_target_consensus,
    fetch_ratios_ttm,
    fetch_stock_peers,
    fetch_treasury_rates,
)

router = APIRouter(tags=["fundamentals"])


def _raise_if_error(data):
    if isinstance(data, dict) and "error" in data:
        raise HTTPException(status_code=500, detail=data["error"])


@router.get("/fundamentals/{symbol}")
async def get_fundamentals(symbol: str, period: str = "annual"):
    symbol = symbol.upper()
    try:
        income = fetch_income_statement(symbol, period)
        balance = fetch_balance_sheet(symbol, period)
        cashflow = fetch_cash_flow(symbol, period)
        if any("error" in d for d in [income, balance, cashflow] if isinstance(d, dict)):
            raise HTTPException(status_code=500, detail="Error fetching financial statements")
        return {"symbol": symbol, "period": period, "income": income, "balance": balance, "cashflow": cashflow}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/financial-growth/{symbol}")
async def get_financial_growth(symbol: str):
    symbol = symbol.upper()
    data = fetch_financial_growth(symbol)
    _raise_if_error(data)
    return {"symbol": symbol, "growth": data}


@router.get("/ratios-ttm/{symbol}")
async def get_ratios_ttm(symbol: str):
    symbol = symbol.upper()
    data = fetch_ratios_ttm(symbol)
    _raise_if_error(data)
    return {"symbol": symbol, "ratios": data}


@router.get("/dcf/{symbol}")
async def get_dcf(symbol: str):
    symbol = symbol.upper()
    data = fetch_dcf(symbol)
    _raise_if_error(data)
    return {"symbol": symbol, "dcf": data}


@router.get("/enterprise-value/{symbol}")
async def get_enterprise_value(symbol: str):
    symbol = symbol.upper()
    data = fetch_enterprise_value(symbol)
    _raise_if_error(data)
    return {"symbol": symbol, "enterpriseValue": data}


@router.get("/key-metrics-ttm/{symbol}")
async def get_key_metrics_ttm(symbol: str):
    symbol = symbol.upper()
    data = fetch_key_metrics_ttm(symbol)
    _raise_if_error(data)
    return {"symbol": symbol, "keyMetrics": data}


@router.get("/financial-scores/{symbol}")
async def get_financial_scores_endpoint(symbol: str):
    data = fetch_financial_scores(symbol.upper())
    _raise_if_error(data)
    return data


@router.get("/owner-earnings/{symbol}")
async def get_owner_earnings(symbol: str):
    symbol = symbol.upper()
    data = fetch_owner_earnings(symbol)
    _raise_if_error(data)
    return {"symbol": symbol, "ownerEarnings": data}


@router.get("/price-target/{symbol}")
async def get_price_target(symbol: str):
    symbol = symbol.upper()
    data = fetch_price_target_consensus(symbol)
    _raise_if_error(data)
    return {"symbol": symbol, "priceTarget": data}


@router.get("/grades/{symbol}")
async def get_grades(symbol: str):
    symbol = symbol.upper()
    data = fetch_grades_consensus(symbol)
    _raise_if_error(data)
    return {"symbol": symbol, "grades": data}


@router.get("/peers/{symbol}")
async def get_peers(symbol: str):
    symbol = symbol.upper()
    data = fetch_stock_peers(symbol)
    _raise_if_error(data)
    return {"symbol": symbol, "peers": data}


@router.get("/earnings-transcript/{symbol}")
async def get_earnings_transcript(
    symbol: str,
    year: Optional[int] = Query(None, description="Year of earnings call"),
    quarter: Optional[int] = Query(None, description="Quarter (1-4)"),
):
    symbol = symbol.upper()
    data = fetch_earnings_transcript(symbol, year, quarter)
    _raise_if_error(data)
    return {"symbol": symbol, "transcripts": data}


@router.get("/earnings-transcript-list/{symbol}")
async def get_earnings_transcripts_list(symbol: str):
    symbol = symbol.upper()
    try:
        data = fetch_earnings_transcripts_list(symbol)
        if isinstance(data, dict) and "error" in data:
            return {"symbol": symbol, "transcripts": []}
        return {"symbol": symbol, "transcripts": data}
    except Exception:
        return {"symbol": symbol, "transcripts": []}


@router.get("/treasury-rates")
async def get_treasury_rates():
    data = fetch_treasury_rates()
    _raise_if_error(data)
    return {"treasuryRates": data}


@router.get("/analyst-estimates/{symbol}")
async def get_analyst_estimates(
    symbol: str,
    period: str = Query("annual", description="annual or quarter"),
    limit: int = Query(5, description="Number of estimates to return"),
):
    symbol = symbol.upper()
    data = fetch_analyst_estimates(symbol, period, limit)
    _raise_if_error(data)
    return {"symbol": symbol, "estimates": data}


@router.get("/press-releases/{symbol}")
async def get_press_releases(symbol: str, limit: int = Query(20, description="Number of releases to return")):
    symbol = symbol.upper()
    try:
        data = fetch_press_releases(symbol, limit)
        if isinstance(data, dict) and "error" in data:
            return {"symbol": symbol, "pressReleases": []}
        if not isinstance(data, list):
            return {"symbol": symbol, "pressReleases": []}
        return {"symbol": symbol, "pressReleases": data}
    except Exception:
        return {"symbol": symbol, "pressReleases": []}
