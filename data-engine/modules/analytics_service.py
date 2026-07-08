"""Patchable service facade for analytics endpoints."""

from __future__ import annotations

from modules import portfolio_analytics as pa
from modules.return_engine import compute_portfolio_returns


def get_portfolio_performance(**kwargs) -> dict:
    return pa.get_portfolio_performance(**kwargs)


def get_holding_metrics(symbol: str, period: str = "2y") -> dict:
    return pa.get_holding_metrics(symbol, period=period)


def run_portfolio_montecarlo(**kwargs) -> dict:
    return pa.run_portfolio_montecarlo(**kwargs)


def get_correlation_matrix(**kwargs) -> dict:
    return pa.get_correlation_matrix(**kwargs)


def get_regime_drift(symbol: str, period: str = "2y") -> dict:
    return pa.get_regime_drift(symbol, period=period)


def get_portfolio_returns(**kwargs) -> dict:
    return compute_portfolio_returns(**kwargs)

