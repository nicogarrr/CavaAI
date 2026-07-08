"""Analytics API routes."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from modules import analytics_service
from modules.cache import cached_call

router = APIRouter(prefix="/analytics", tags=["analytics"])


class PortfolioAnalyticsRequest(BaseModel):
    symbols: List[str]
    weights: Optional[List[float]] = None
    period: str = "2y"
    rf: float = 0.0
    benchmark: str = "SPY"


class MonteCarloRequest(BaseModel):
    symbols: List[str]
    weights: Optional[List[float]] = None
    period: str = "3y"
    horizon: int = 252
    sims: int = 1000
    bust: float = -0.5
    goal: float = 0.5
    models: Optional[List[str]] = None


class CorrelationRequest(BaseModel):
    symbols: List[str]
    period: str = "1y"
    method: str = "pearson"


class TransactionLike(BaseModel):
    symbol: str
    type: str
    quantity: float
    price: float
    date: str


class PortfolioReturnsRequest(BaseModel):
    symbols: Optional[List[str]] = None
    transactions: Optional[List[TransactionLike]] = None
    period: str = "2y"


@router.post("/portfolio")
async def portfolio_analytics(req: PortfolioAnalyticsRequest):
    if not req.symbols:
        raise HTTPException(status_code=400, detail="symbols list cannot be empty")
    if len(req.symbols) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 symbols per request")

    symbols = [s.upper().strip() for s in req.symbols]
    result = analytics_service.get_portfolio_performance(
        symbols=symbols,
        weights=req.weights,
        period=req.period,
        rf=req.rf,
        benchmark=req.benchmark,
    )
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return result


@router.post("/portfolio/returns")
async def portfolio_returns(req: PortfolioReturnsRequest):
    transactions = [t.model_dump() for t in req.transactions or []]
    symbols = [s.upper().strip() for s in req.symbols or []]
    result = analytics_service.get_portfolio_returns(
        transactions=transactions,
        symbols=symbols,
        period=req.period,
    )
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return result


@router.get("/holding/{symbol}")
async def holding_analytics(symbol: str, period: str = Query("2y", description="yfinance period string")):
    cache_key = f"analytics:holding:{symbol.upper()}:{period}"
    result = cached_call(
        cache_key,
        lambda: analytics_service.get_holding_metrics(symbol.upper(), period=period),
        ttl_seconds=300,
    )
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return result


@router.post("/montecarlo")
async def portfolio_montecarlo(req: MonteCarloRequest):
    if not req.symbols:
        raise HTTPException(status_code=400, detail="symbols list cannot be empty")

    symbols = [s.upper().strip() for s in req.symbols]
    result = analytics_service.run_portfolio_montecarlo(
        symbols=symbols,
        weights=req.weights,
        period=req.period,
        horizon=req.horizon,
        sims=req.sims,
        bust=req.bust,
        goal=req.goal,
        models=req.models,
    )
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return result


@router.post("/correlation")
async def correlation_matrix(req: CorrelationRequest):
    if len(req.symbols) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 symbols for correlation")

    symbols = [s.upper().strip() for s in req.symbols]
    result = analytics_service.get_correlation_matrix(
        symbols=symbols,
        period=req.period,
        method=req.method,
    )
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return result


@router.get("/regime/{symbol}")
async def regime_drift(symbol: str, period: str = Query("2y", description="yfinance period string")):
    result = analytics_service.get_regime_drift(symbol.upper(), period=period)
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return result

