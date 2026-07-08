"""
Portfolio Analytics Module
Wraps quantstats-pro for real performance metrics, Monte Carlo, and correlation.
All functions return plain dicts/lists — no DataFrame objects leave this module.
"""

from __future__ import annotations
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

import quantstats as qs
from quantstats.montecarlo import run_models


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch_returns(symbol: str, period: str = "2y") -> Optional[pd.Series]:
    """Download adjusted close prices and return daily log returns."""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period, auto_adjust=True)
        if hist.empty or len(hist) < 30:
            return None
        prices = hist["Close"].dropna()
        returns = prices.pct_change().dropna()
        returns.name = symbol
        return returns
    except Exception:
        return None


def _fetch_multi_returns(symbols: list[str], period: str = "2y") -> pd.DataFrame:
    """Fetch aligned daily returns for multiple symbols (inner join on dates)."""
    series_map: dict[str, pd.Series] = {}
    for sym in symbols:
        r = _fetch_returns(sym, period)
        if r is not None and not r.empty:
            series_map[sym] = r

    if not series_map:
        return pd.DataFrame()

    df = pd.DataFrame(series_map)
    # Inner join: only dates present for ALL symbols
    df = df.dropna()
    return df


def _safe_float(val) -> Optional[float]:
    """Convert numpy/pandas scalar to Python float, or None if NaN/inf."""
    if val is None:
        return None
    try:
        f = float(val)
        return None if (np.isnan(f) or np.isinf(f)) else round(f, 6)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Portfolio performance metrics (single-series)
# ---------------------------------------------------------------------------

def get_portfolio_performance(
    symbols: list[str],
    weights: Optional[list[float]] = None,
    period: str = "2y",
    rf: float = 0.0,
    benchmark: str = "SPY",
) -> dict:
    """
    Compute real performance metrics for a weighted portfolio of symbols
    using quantstats-pro.

    Returns a dict with metrics grouped by category.
    Returns {"error": "..."} if data is insufficient.
    """
    df = _fetch_multi_returns(symbols, period)
    if df.empty or len(df) < 30:
        return {"error": "Insufficient price history to compute metrics", "symbols": symbols}

    # Normalise weights
    n = len(df.columns)
    if weights is None or len(weights) != n:
        w = np.array([1.0 / n] * n)
    else:
        w = np.array(weights, dtype=float)
        w = w / w.sum()

    portfolio_returns: pd.Series = (df * w).sum(axis=1)
    portfolio_returns.name = "portfolio"

    # Benchmark
    bench_returns: Optional[pd.Series] = None
    if benchmark:
        bench_series = _fetch_returns(benchmark, period)
        if bench_series is not None:
            # Align to portfolio dates
            aligned = pd.concat([portfolio_returns, bench_series], axis=1).dropna()
            if len(aligned) >= 30:
                portfolio_returns = aligned.iloc[:, 0]
                bench_returns = aligned.iloc[:, 1]

    metrics: dict = {}

    # Return metrics
    metrics["cagr"] = _safe_float(qs.stats.cagr(portfolio_returns))
    metrics["volatility_ann"] = _safe_float(qs.stats.volatility(portfolio_returns))
    metrics["max_drawdown"] = _safe_float(qs.stats.max_drawdown(portfolio_returns))
    metrics["calmar"] = _safe_float(qs.stats.calmar(portfolio_returns))
    metrics["sharpe"] = _safe_float(qs.stats.sharpe(portfolio_returns, rf=rf))
    metrics["sortino"] = _safe_float(qs.stats.sortino(portfolio_returns, rf=rf))
    metrics["omega"] = _safe_float(qs.stats.omega(portfolio_returns, rf=rf))

    # Risk metrics
    metrics["var_95"] = _safe_float(qs.stats.value_at_risk(portfolio_returns, confidence=0.95))
    metrics["cvar_95"] = _safe_float(qs.stats.conditional_value_at_risk(portfolio_returns, confidence=0.95))
    metrics["skew"] = _safe_float(qs.stats.skew(portfolio_returns))
    metrics["kurtosis"] = _safe_float(qs.stats.kurtosis(portfolio_returns))

    # Win/loss
    metrics["win_rate"] = _safe_float(qs.stats.win_rate(portfolio_returns))
    metrics["avg_win"] = _safe_float(qs.stats.avg_win(portfolio_returns))
    metrics["avg_loss"] = _safe_float(qs.stats.avg_loss(portfolio_returns))
    metrics["payoff_ratio"] = _safe_float(qs.stats.payoff_ratio(portfolio_returns))
    metrics["profit_factor"] = _safe_float(qs.stats.profit_factor(portfolio_returns))

    # Benchmark-relative metrics (only if benchmark available)
    if bench_returns is not None:
        metrics["r_squared"] = _safe_float(qs.stats.r_squared(portfolio_returns, bench_returns))
        greeks = qs.stats.greeks(portfolio_returns, bench_returns)
        if hasattr(greeks, "alpha"):
            metrics["alpha"] = _safe_float(greeks.alpha)
            metrics["beta"] = _safe_float(greeks.beta)
        metrics["information_ratio"] = _safe_float(
            qs.stats.information_ratio(portfolio_returns, bench_returns)
        )

    # Derived scores (0–100 normalised, replacing heuristic placeholders)
    sharpe = metrics.get("sharpe") or 0.0
    cagr = metrics.get("cagr") or 0.0
    dd = abs(metrics.get("max_drawdown") or 0.0)
    wr = (metrics.get("win_rate") or 0.0) * 100  # already 0-1 from qs

    # quality: risk-adjusted return composite
    quality_raw = 50 + (sharpe * 15) + (wr - 50) * 0.3
    metrics["score_quality"] = int(min(100, max(0, quality_raw)))

    # growth: annualised return normalised [-30%, +50%] → [0, 100]
    growth_raw = ((cagr + 0.30) / 0.80) * 100
    metrics["score_growth"] = int(min(100, max(0, growth_raw)))

    # value: inverse of max drawdown severity
    value_raw = max(0, 100 - dd * 150)
    metrics["score_value"] = int(min(100, max(0, value_raw)))

    # cagr3y proxy (same series; a proper 3Y window should use 756 days)
    metrics["score_cagr3y"] = _safe_float(cagr * 100)

    # Periods used
    metrics["trading_days"] = len(portfolio_returns)
    metrics["start_date"] = str(portfolio_returns.index[0].date())
    metrics["end_date"] = str(portfolio_returns.index[-1].date())

    return metrics


# ---------------------------------------------------------------------------
# Per-holding individual metrics
# ---------------------------------------------------------------------------

def get_holding_metrics(symbol: str, period: str = "2y") -> dict:
    """Compute real performance metrics for a single holding."""
    returns = _fetch_returns(symbol, period)
    if returns is None or returns.empty:
        return {"symbol": symbol, "error": "Insufficient price history"}

    return {
        "symbol": symbol,
        "cagr": _safe_float(qs.stats.cagr(returns)),
        "volatility_ann": _safe_float(qs.stats.volatility(returns)),
        "max_drawdown": _safe_float(qs.stats.max_drawdown(returns)),
        "sharpe": _safe_float(qs.stats.sharpe(returns)),
        "sortino": _safe_float(qs.stats.sortino(returns)),
        "var_95": _safe_float(qs.stats.value_at_risk(returns, confidence=0.95)),
        "cvar_95": _safe_float(qs.stats.conditional_value_at_risk(returns, confidence=0.95)),
        "win_rate": _safe_float(qs.stats.win_rate(returns)),
        "calmar": _safe_float(qs.stats.calmar(returns)),
        "trading_days": len(returns),
    }


# ---------------------------------------------------------------------------
# Monte Carlo
# ---------------------------------------------------------------------------

def run_portfolio_montecarlo(
    symbols: list[str],
    weights: Optional[list[float]] = None,
    period: str = "3y",
    horizon: int = 252,
    sims: int = 1000,
    bust: float = -0.5,
    goal: float = 0.5,
    models: Optional[list[str]] = None,
) -> dict:
    """
    Run multi-model Monte Carlo simulation on a weighted portfolio.

    Returns a dict with per-model results and a summary.
    """
    df = _fetch_multi_returns(symbols, period)
    if df.empty or len(df) < 60:
        return {"error": "Insufficient price history for Monte Carlo", "symbols": symbols}

    n = len(df.columns)
    if weights is None or len(weights) != n:
        w = np.array([1.0 / n] * n)
    else:
        w = np.array(weights, dtype=float)
        w = w / w.sum()

    portfolio_returns: pd.Series = (df * w).sum(axis=1)

    # Default models: fast + robust set for portfolio use
    default_models = ["gbm", "bootstrap", "block_bootstrap", "garch"]
    model_names = models if models else default_models

    try:
        # run_models returns dict[str, ModelResult]
        model_results: dict = run_models(
            portfolio_returns,
            horizon=horizon,
            sims=sims,
            bust=bust,
            goal=goal,
            models=model_names,
        )
    except Exception as exc:
        return {"error": f"Monte Carlo failed: {exc}", "symbols": symbols}

    output: dict = {
        "symbols": symbols,
        "horizon_days": horizon,
        "simulations": sims,
        "bust_threshold": bust,
        "goal_threshold": goal,
        "models": {},
    }

    all_medians: list[float] = []

    for model_name, result in model_results.items():
        try:
            # terminal_values() returns the final cumulative return per simulation
            fc = result.terminal_values()
            fc = fc[np.isfinite(fc)]
            if len(fc) == 0:
                continue

            # result.bust / result.goal store the thresholds, not probabilities
            bust_prob = _safe_float(float((fc < bust).mean())) if len(fc) > 0 else None
            goal_prob = _safe_float(float((fc > goal).mean())) if len(fc) > 0 else None

            model_out = {
                "name": result.name,
                "label": result.label,
                "category": result.category,
                "bust_probability": bust_prob,
                "goal_probability": goal_prob,
                "percentile_5": _safe_float(np.percentile(fc, 5)),
                "percentile_25": _safe_float(np.percentile(fc, 25)),
                "median": _safe_float(np.percentile(fc, 50)),
                "percentile_75": _safe_float(np.percentile(fc, 75)),
                "percentile_95": _safe_float(np.percentile(fc, 95)),
                "mean": _safe_float(float(fc.mean())),
                "std": _safe_float(float(fc.std())),
            }
            output["models"][model_name] = model_out

            med = model_out["median"]
            if med is not None:
                all_medians.append(med)
        except Exception:
            continue

    # Cross-model summary
    if all_medians:
        output["summary"] = {
            "cross_model_median_return": _safe_float(float(np.median(all_medians))),
            "models_run": len(output["models"]),
            "conservative_envelope": _safe_float(float(np.min(all_medians))),
        }
    else:
        output["summary"] = {"error": "No model produced valid results"}

    return output


# ---------------------------------------------------------------------------
# Correlation
# ---------------------------------------------------------------------------

def get_correlation_matrix(
    symbols: list[str],
    period: str = "1y",
    method: str = "pearson",
) -> dict:
    """
    Compute pairwise correlation on aligned daily returns.

    Uses inner join by date — no imputation, no fill.
    Returns full matrix plus pairwise list for UI consumption.
    """
    df = _fetch_multi_returns(symbols, period)
    if df.empty or df.shape[1] < 2:
        return {
            "error": "Insufficient data for correlation",
            "symbols": symbols,
            "trading_days": len(df) if not df.empty else 0,
        }

    corr = df.corr(method=method)

    # Full matrix as nested dict (JSON-serialisable)
    matrix: dict[str, dict[str, Optional[float]]] = {}
    for sym_i in corr.index:
        matrix[sym_i] = {}
        for sym_j in corr.columns:
            matrix[sym_i][sym_j] = _safe_float(corr.loc[sym_i, sym_j])

    # Pairwise list sorted by absolute correlation (excluding self-pairs)
    pairs: list[dict] = []
    seen: set[frozenset] = set()
    for sym_i in corr.index:
        for sym_j in corr.columns:
            key = frozenset({sym_i, sym_j})
            if sym_i == sym_j or key in seen:
                continue
            seen.add(key)
            val = _safe_float(corr.loc[sym_i, sym_j])
            pairs.append({
                "symbol_a": sym_i,
                "symbol_b": sym_j,
                "correlation": val,
                "abs_correlation": abs(val) if val is not None else None,
                "level": (
                    "high" if val is not None and abs(val) >= 0.7
                    else "medium" if val is not None and abs(val) >= 0.4
                    else "low"
                ),
            })

    pairs.sort(key=lambda x: x["abs_correlation"] or 0.0, reverse=True)

    return {
        "symbols": list(df.columns),
        "trading_days": len(df),
        "period": period,
        "method": method,
        "matrix": matrix,
        "pairs": pairs,
    }


# ---------------------------------------------------------------------------
# Alpha Decay / Regime Drift
# ---------------------------------------------------------------------------

def get_regime_drift(symbol: str, period: str = "2y") -> dict:
    """
    Run alpha decay analysis on a single holding to detect regime drift.
    Uses quantstats-pro alphadecay module.
    """
    try:
        from quantstats.alphadecay import core as ad
    except ImportError:
        return {"symbol": symbol, "error": "alphadecay module not available"}

    returns = _fetch_returns(symbol, period)
    if returns is None or len(returns) < 60:
        return {"symbol": symbol, "error": "Insufficient data for drift analysis"}

    try:
        result = ad.compute_decay(returns)
        # result is a DecayResult dataclass; convert to dict
        out: dict = {"symbol": symbol}
        for field in result.__dataclass_fields__:
            val = getattr(result, field)
            if isinstance(val, pd.DataFrame):
                out[field] = val.to_dict(orient="records")
            elif isinstance(val, pd.Series):
                out[field] = val.to_dict()
            elif isinstance(val, (np.integer, np.floating)):
                out[field] = _safe_float(val)
            else:
                out[field] = val
        return out
    except Exception as exc:
        return {"symbol": symbol, "error": f"Drift analysis failed: {exc}"}
