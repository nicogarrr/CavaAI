from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from modules.fmp import (
    fetch_income_statement,
    fetch_balance_sheet,
    fetch_cash_flow,
    fetch_financial_growth,
    fetch_ratios_ttm,
    fetch_dcf,
    fetch_enterprise_value,
    fetch_key_metrics_ttm,
    fetch_financial_scores,
    fetch_owner_earnings,
    fetch_price_target_consensus,
    fetch_grades_consensus,
    fetch_stock_peers,
    # Priority APIs
    fetch_earnings_transcript,
    fetch_insider_trading,
    fetch_treasury_rates,
    fetch_analyst_estimates,
    fetch_press_releases
)

app = FastAPI(title="FMP Data Engine", version="1.0.0")

# CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"status": "ok", "service": "FMP Data Engine"}

@app.get("/fundamentals/{symbol}")
async def get_fundamentals(symbol: str, period: str = "annual"):
    """Get combined financial statements (Income, Balance, CashFlow)"""
    symbol = symbol.upper()
    try:
        income = fetch_income_statement(symbol, period)
        balance = fetch_balance_sheet(symbol, period)
        cashflow = fetch_cash_flow(symbol, period)
        
        if any('error' in d for d in [income, balance, cashflow] if isinstance(d, dict)):
            raise HTTPException(status_code=500, detail="Error fetching financial statements")
        
        return {
            "symbol": symbol,
            "period": period,
            "income": income,
            "balance": balance,
            "cashflow": cashflow
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/financial-growth/{symbol}")
async def get_financial_growth(symbol: str):
    """Get pre-calculated growth metrics (revenue, EPS, FCF growth)"""
    symbol = symbol.upper()
    try:
        data = fetch_financial_growth(symbol)
        if isinstance(data, dict) and 'error' in data:
            raise HTTPException(status_code=500, detail=data['error'])
        return {"symbol": symbol, "growth": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/ratios-ttm/{symbol}")
async def get_ratios_ttm(symbol: str):
    """Get TTM ratios (PER, ROIC, ROE, P/S, P/B, etc.)"""
    symbol = symbol.upper()
    try:
        data = fetch_ratios_ttm(symbol)
        if isinstance(data, dict) and 'error' in data:
            raise HTTPException(status_code=500, detail=data['error'])
        return {"symbol": symbol, "ratios": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/dcf/{symbol}")
async def get_dcf(symbol: str):
    """Get Discounted Cash Flow valuation (intrinsic value)"""
    symbol = symbol.upper()
    try:
        data = fetch_dcf(symbol)
        if isinstance(data, dict) and 'error' in data:
            raise HTTPException(status_code=500, detail=data['error'])
        return {"symbol": symbol, "dcf": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/enterprise-value/{symbol}")
async def get_enterprise_value(symbol: str):
    """Get Enterprise Value data (for EV/EBITDA, EV/FCF)"""
    symbol = symbol.upper()
    try:
        data = fetch_enterprise_value(symbol)
        if isinstance(data, dict) and 'error' in data:
            raise HTTPException(status_code=500, detail=data['error'])
        return {"symbol": symbol, "enterpriseValue": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/key-metrics-ttm/{symbol}")
async def get_key_metrics_ttm(symbol: str):
    """Get Key Metrics TTM (ROE, ROIC, EV/EBITDA, Graham Number, etc.)"""
    symbol = symbol.upper()
    try:
        data = fetch_key_metrics_ttm(symbol)
        if isinstance(data, dict) and 'error' in data:
            raise HTTPException(status_code=500, detail=data['error'])
        return {"symbol": symbol, "keyMetrics": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/financial-scores/{symbol}")
async def get_financial_scores(symbol: str):
    """Get Financial Scores (Altman Z-Score + Piotroski Score)"""
    symbol = symbol.upper()
    try:
        data = fetch_financial_scores(symbol)
        if isinstance(data, dict) and 'error' in data:
            raise HTTPException(status_code=500, detail=data['error'])
        return {"symbol": symbol, "scores": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/owner-earnings/{symbol}")
async def get_owner_earnings(symbol: str):
    """Get Owner Earnings (Buffett's preferred metric)"""
    symbol = symbol.upper()
    try:
        data = fetch_owner_earnings(symbol)
        if isinstance(data, dict) and 'error' in data:
            raise HTTPException(status_code=500, detail=data['error'])
        return {"symbol": symbol, "ownerEarnings": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/price-target/{symbol}")
async def get_price_target(symbol: str):
    """Get Analyst Price Target Consensus"""
    symbol = symbol.upper()
    try:
        data = fetch_price_target_consensus(symbol)
        if isinstance(data, dict) and 'error' in data:
            raise HTTPException(status_code=500, detail=data['error'])
        return {"symbol": symbol, "priceTarget": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/grades/{symbol}")
async def get_grades(symbol: str):
    """Get Stock Grades Consensus (Buy/Hold/Sell)"""
    symbol = symbol.upper()
    try:
        data = fetch_grades_consensus(symbol)
        if isinstance(data, dict) and 'error' in data:
            raise HTTPException(status_code=500, detail=data['error'])
        return {"symbol": symbol, "grades": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/peers/{symbol}")
async def get_peers(symbol: str):
    """Get Stock Peers for comparison"""
    symbol = symbol.upper()
    try:
        data = fetch_stock_peers(symbol)
        if isinstance(data, dict) and 'error' in data:
            raise HTTPException(status_code=500, detail=data['error'])
        return {"symbol": symbol, "peers": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# PRIORITY APIs - AI/RAG, Trading Signals, WACC
# ============================================================================

@app.get("/earnings-transcript/{symbol}")
async def get_earnings_transcript(
    symbol: str,
    year: Optional[int] = Query(None, description="Year of earnings call"),
    quarter: Optional[int] = Query(None, description="Quarter (1-4)")
):
    """Get Earnings Call Transcript for AI/RAG analysis"""
    symbol = symbol.upper()
    try:
        data = fetch_earnings_transcript(symbol, year, quarter)
        if isinstance(data, dict) and 'error' in data:
            raise HTTPException(status_code=500, detail=data['error'])
        return {"symbol": symbol, "transcripts": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/insider-trading/{symbol}")
async def get_insider_trading(
    symbol: str,
    limit: int = Query(50, description="Number of transactions to return")
):
    """Get Insider Trading data (CEO/CFO buy/sell signals)"""
    symbol = symbol.upper()
    try:
        data = fetch_insider_trading(symbol, limit)
        if isinstance(data, dict) and 'error' in data:
            raise HTTPException(status_code=500, detail=data['error'])
        return {"symbol": symbol, "insiderTrades": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/treasury-rates")
async def get_treasury_rates():
    """Get Treasury Rates (10Y for Risk-Free Rate in WACC)"""
    try:
        data = fetch_treasury_rates()
        if isinstance(data, dict) and 'error' in data:
            raise HTTPException(status_code=500, detail=data['error'])
        return {"treasuryRates": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/analyst-estimates/{symbol}")
async def get_analyst_estimates(
    symbol: str,
    period: str = Query("annual", description="annual or quarter"),
    limit: int = Query(5, description="Number of estimates to return")
):
    """Get Analyst Estimates (Future EPS/Revenue projections)"""
    symbol = symbol.upper()
    try:
        data = fetch_analyst_estimates(symbol, period, limit)
        if isinstance(data, dict) and 'error' in data:
            raise HTTPException(status_code=500, detail=data['error'])
        return {"symbol": symbol, "estimates": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/press-releases/{symbol}")
async def get_press_releases(
    symbol: str,
    limit: int = Query(20, description="Number of releases to return")
):
    """Get Official Press Releases"""
    symbol = symbol.upper()
    try:
        data = fetch_press_releases(symbol, limit)
        if isinstance(data, dict) and 'error' in data:
            raise HTTPException(status_code=500, detail=data['error'])
        return {"symbol": symbol, "pressReleases": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
