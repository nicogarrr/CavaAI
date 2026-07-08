"""
Integration tests for the /analytics/* FastAPI endpoints.
Uses TestClient so no network or docker required.
Mocks portfolio_analytics so no external calls are made.

Run from data-engine/:
    pytest tests/test_analytics_endpoints.py -v
"""

import sys
import os
import pytest
import numpy as np
import pandas as pd

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------

def _synth_perf_result():
    return {
        "cagr": 0.12, "volatility_ann": 0.18, "max_drawdown": -0.22,
        "sharpe": 0.75, "sortino": 0.90, "omega": 1.4,
        "var_95": -0.018, "cvar_95": -0.025, "skew": -0.3, "kurtosis": 3.2,
        "win_rate": 0.54, "avg_win": 0.009, "avg_loss": -0.007,
        "payoff_ratio": 1.2, "profit_factor": 1.3,
        "score_quality": 65, "score_growth": 55, "score_value": 70,
        "score_cagr3y": 12.0, "trading_days": 504,
        "start_date": "2023-01-02", "end_date": "2024-12-31",
    }


def _synth_mc_result():
    return {
        "symbols": ["AAPL", "MSFT"],
        "horizon_days": 252, "simulations": 100,
        "bust_threshold": -0.5, "goal_threshold": 0.5,
        "models": {
            "gbm": {
                "name": "gbm", "label": "GBM", "category": "parametric",
                "bust_probability": 0.02, "goal_probability": 0.35,
                "percentile_5": -0.25, "percentile_25": -0.05,
                "median": 0.08, "percentile_75": 0.22, "percentile_95": 0.45,
                "mean": 0.09, "std": 0.21,
            }
        },
        "summary": {
            "cross_model_median_return": 0.08,
            "models_run": 1,
            "conservative_envelope": 0.08,
        },
    }


def _synth_corr_result():
    return {
        "symbols": ["AAPL", "MSFT"],
        "trading_days": 252, "period": "1y", "method": "pearson",
        "matrix": {
            "AAPL": {"AAPL": 1.0, "MSFT": 0.82},
            "MSFT": {"AAPL": 0.82, "MSFT": 1.0},
        },
        "pairs": [
            {
                "symbol_a": "AAPL", "symbol_b": "MSFT",
                "correlation": 0.82, "abs_correlation": 0.82, "level": "high",
            }
        ],
    }


def _synth_holding_result():
    return {
        "symbol": "AAPL",
        "cagr": 0.25, "volatility_ann": 0.28, "max_drawdown": -0.32,
        "sharpe": 1.1, "sortino": 1.4, "var_95": -0.022,
        "cvar_95": -0.031, "win_rate": 0.55, "calmar": 0.78,
        "trading_days": 504,
    }


# ---------------------------------------------------------------------------
# Client fixture with mocked analytics functions
# ---------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    import modules.analytics_service as analytics_service

    monkeypatch.setattr(analytics_service, "get_portfolio_performance", lambda **kw: _synth_perf_result())
    monkeypatch.setattr(analytics_service, "get_holding_metrics", lambda symbol, period="2y": _synth_holding_result())
    monkeypatch.setattr(analytics_service, "run_portfolio_montecarlo", lambda **kw: _synth_mc_result())
    monkeypatch.setattr(analytics_service, "get_correlation_matrix", lambda **kw: _synth_corr_result())
    monkeypatch.setattr(analytics_service, "get_portfolio_returns", lambda **kw: {
        "dates": ["2024-01-01", "2024-01-02"],
        "nav": [100.0, 101.0],
        "daily_returns": [0.0, 0.01],
        "twr": 0.01,
        "start_date": "2024-01-01",
        "end_date": "2024-01-02",
    })

    import main as app_module

    return TestClient(app_module.app)


# ---------------------------------------------------------------------------
# /analytics/portfolio
# ---------------------------------------------------------------------------

class TestPortfolioAnalyticsEndpoint:
    def test_success(self, client):
        resp = client.post("/analytics/portfolio", json={"symbols": ["AAPL", "MSFT"]})
        assert resp.status_code == 200
        data = resp.json()
        assert "sharpe" in data
        assert "score_quality" in data

    def test_empty_symbols_returns_400(self, client):
        resp = client.post("/analytics/portfolio", json={"symbols": []})
        assert resp.status_code == 400

    def test_too_many_symbols_returns_400(self, client):
        resp = client.post("/analytics/portfolio", json={"symbols": [f"SYM{i}" for i in range(51)]})
        assert resp.status_code == 400

    def test_weights_accepted(self, client):
        resp = client.post("/analytics/portfolio", json={
            "symbols": ["AAPL", "MSFT"],
            "weights": [0.6, 0.4],
        })
        assert resp.status_code == 200

    def test_returns_error_when_backend_says_so(self, monkeypatch, client):
        import modules.analytics_service as analytics_service
        monkeypatch.setattr(analytics_service, "get_portfolio_performance", lambda **kw: {"error": "Insufficient data"})
        resp = client.post("/analytics/portfolio", json={"symbols": ["ZZZZ"]})
        assert resp.status_code == 422

    def test_returns_endpoint_success(self, client):
        resp = client.post("/analytics/portfolio/returns", json={
            "symbols": ["AAPL"],
            "transactions": [{
                "symbol": "AAPL",
                "type": "buy",
                "quantity": 1,
                "price": 100,
                "date": "2024-01-01",
            }],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["twr"] == 0.01
        assert data["nav"] == [100.0, 101.0]


# ---------------------------------------------------------------------------
# /analytics/holding/{symbol}
# ---------------------------------------------------------------------------

class TestHoldingAnalyticsEndpoint:
    def test_success(self, client):
        resp = client.get("/analytics/holding/AAPL")
        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "AAPL"
        assert "sharpe" in data

    def test_period_query_param(self, client):
        resp = client.get("/analytics/holding/MSFT?period=1y")
        assert resp.status_code == 200

    def test_symbol_uppercased(self, client):
        resp = client.get("/analytics/holding/aapl")
        assert resp.status_code == 200
        assert resp.json()["symbol"] == "AAPL"


# ---------------------------------------------------------------------------
# /analytics/montecarlo
# ---------------------------------------------------------------------------

class TestMonteCarloEndpoint:
    def test_success(self, client):
        resp = client.post("/analytics/montecarlo", json={"symbols": ["AAPL", "MSFT"]})
        assert resp.status_code == 200
        data = resp.json()
        assert "models" in data
        assert "summary" in data

    def test_empty_symbols_returns_400(self, client):
        resp = client.post("/analytics/montecarlo", json={"symbols": []})
        assert resp.status_code == 400

    def test_custom_params_accepted(self, client):
        resp = client.post("/analytics/montecarlo", json={
            "symbols": ["AAPL"],
            "horizon": 126,
            "sims": 200,
            "bust": -0.4,
            "goal": 0.3,
            "models": ["gbm"],
        })
        assert resp.status_code == 200

    def test_error_propagated(self, monkeypatch, client):
        import modules.analytics_service as analytics_service
        monkeypatch.setattr(analytics_service, "run_portfolio_montecarlo", lambda **kw: {"error": "No data"})
        resp = client.post("/analytics/montecarlo", json={"symbols": ["ZZZZ"]})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /analytics/correlation
# ---------------------------------------------------------------------------

class TestCorrelationEndpoint:
    def test_success(self, client):
        resp = client.post("/analytics/correlation", json={"symbols": ["AAPL", "MSFT"]})
        assert resp.status_code == 200
        data = resp.json()
        assert "matrix" in data
        assert "pairs" in data

    def test_single_symbol_returns_400(self, client):
        resp = client.post("/analytics/correlation", json={"symbols": ["AAPL"]})
        assert resp.status_code == 400

    def test_method_spearman(self, client):
        resp = client.post("/analytics/correlation", json={
            "symbols": ["AAPL", "MSFT"],
            "method": "spearman",
        })
        assert resp.status_code == 200

    def test_period_param(self, client):
        resp = client.post("/analytics/correlation", json={
            "symbols": ["AAPL", "MSFT"],
            "period": "6mo",
        })
        assert resp.status_code == 200

    def test_error_propagated(self, monkeypatch, client):
        import modules.analytics_service as analytics_service
        monkeypatch.setattr(analytics_service, "get_correlation_matrix", lambda **kw: {"error": "No data"})
        resp = client.post("/analytics/correlation", json={"symbols": ["ZZZ", "YYY"]})
        assert resp.status_code == 422
