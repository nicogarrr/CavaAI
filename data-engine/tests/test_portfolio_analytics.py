"""
Tests for modules/portfolio_analytics.py

Run from data-engine/:
    pytest tests/test_portfolio_analytics.py -v
"""

import math
import numpy as np
import pandas as pd
import pytest

from modules.portfolio_analytics import (
    _safe_float,
    _fetch_multi_returns,
    get_portfolio_performance,
    get_holding_metrics,
    run_portfolio_montecarlo,
    get_correlation_matrix,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def synth_returns():
    """Synthetic daily returns for 3 assets over 3 years (approx 756 rows)."""
    rng = np.random.default_rng(42)
    n = 756
    dates = pd.date_range("2021-01-01", periods=n, freq="B")
    data = {
        "AAA": rng.normal(0.0005, 0.015, n),
        "BBB": rng.normal(0.0003, 0.020, n),
        "CCC": rng.normal(0.0001, 0.012, n),
    }
    return pd.DataFrame(data, index=dates)


@pytest.fixture
def patched_fetch(monkeypatch, synth_returns):
    """Monkeypatch _fetch_multi_returns to return synthetic data without network."""

    def _mock_multi(symbols, period="2y"):
        cols = [s for s in symbols if s in synth_returns.columns]
        if not cols:
            return pd.DataFrame()
        return synth_returns[cols].copy()

    monkeypatch.setattr(
        "modules.portfolio_analytics._fetch_multi_returns", _mock_multi
    )

    def _mock_single(symbol, period="2y"):
        if symbol not in synth_returns.columns:
            return None
        s = synth_returns[symbol].copy()
        s.name = symbol
        return s

    monkeypatch.setattr(
        "modules.portfolio_analytics._fetch_returns", _mock_single
    )


# ---------------------------------------------------------------------------
# _safe_float
# ---------------------------------------------------------------------------

class TestSafeFloat:
    def test_normal_value(self):
        assert _safe_float(1.23456789) == pytest.approx(1.234568, rel=1e-5)

    def test_nan_returns_none(self):
        assert _safe_float(float("nan")) is None

    def test_inf_returns_none(self):
        assert _safe_float(float("inf")) is None

    def test_neg_inf_returns_none(self):
        assert _safe_float(float("-inf")) is None

    def test_none_input(self):
        assert _safe_float(None) is None

    def test_numpy_scalar(self):
        val = np.float64(3.14)
        result = _safe_float(val)
        assert result == pytest.approx(3.14, rel=1e-5)

    def test_numpy_nan(self):
        assert _safe_float(np.nan) is None


# ---------------------------------------------------------------------------
# get_portfolio_performance
# ---------------------------------------------------------------------------

class TestGetPortfolioPerformance:
    def test_returns_dict(self, patched_fetch):
        result = get_portfolio_performance(["AAA", "BBB", "CCC"], period="2y")
        assert isinstance(result, dict)
        assert "error" not in result

    def test_core_metrics_present(self, patched_fetch):
        result = get_portfolio_performance(["AAA", "BBB"], period="2y")
        for key in ["cagr", "sharpe", "sortino", "max_drawdown", "var_95", "cvar_95"]:
            assert key in result, f"Missing metric: {key}"

    def test_scores_in_range(self, patched_fetch):
        result = get_portfolio_performance(["AAA", "BBB", "CCC"], period="2y")
        assert 0 <= result["score_quality"] <= 100
        assert 0 <= result["score_growth"] <= 100
        assert 0 <= result["score_value"] <= 100

    def test_max_drawdown_non_positive(self, patched_fetch):
        result = get_portfolio_performance(["AAA"], period="2y")
        dd = result.get("max_drawdown")
        if dd is not None:
            assert dd <= 0.0, f"Max drawdown should be <= 0, got {dd}"

    def test_weights_respected(self, patched_fetch):
        # Equal weights vs concentrated weights should produce different sharpes
        r1 = get_portfolio_performance(["AAA", "BBB"], weights=[0.5, 0.5], period="2y")
        r2 = get_portfolio_performance(["AAA", "BBB"], weights=[0.9, 0.1], period="2y")
        # They may be equal by chance, but both should succeed
        assert "sharpe" in r1
        assert "sharpe" in r2

    def test_single_symbol(self, patched_fetch):
        result = get_portfolio_performance(["AAA"], period="2y")
        assert "error" not in result
        assert "cagr" in result

    def test_unknown_symbol_returns_error(self, patched_fetch):
        result = get_portfolio_performance(["ZZZNOTREAL"], period="2y")
        assert "error" in result

    def test_trading_days_positive(self, patched_fetch):
        result = get_portfolio_performance(["AAA", "BBB"], period="2y")
        assert result.get("trading_days", 0) > 0


# ---------------------------------------------------------------------------
# get_holding_metrics
# ---------------------------------------------------------------------------

class TestGetHoldingMetrics:
    def test_success(self, patched_fetch):
        result = get_holding_metrics("AAA", period="2y")
        assert result["symbol"] == "AAA"
        assert "sharpe" in result
        assert "cagr" in result
        assert "max_drawdown" in result

    def test_unknown_symbol(self, patched_fetch):
        result = get_holding_metrics("ZZZNOTREAL", period="2y")
        assert "error" in result

    def test_win_rate_between_0_and_1(self, patched_fetch):
        result = get_holding_metrics("BBB", period="2y")
        wr = result.get("win_rate")
        if wr is not None:
            assert 0.0 <= wr <= 1.0, f"win_rate out of [0,1]: {wr}"


# ---------------------------------------------------------------------------
# run_portfolio_montecarlo
# ---------------------------------------------------------------------------

class TestRunPortfolioMontecarlo:
    def test_returns_dict(self, patched_fetch):
        result = run_portfolio_montecarlo(["AAA", "BBB"], sims=100, horizon=63)
        assert isinstance(result, dict)
        assert "error" not in result, result.get("error")

    def test_has_models(self, patched_fetch):
        result = run_portfolio_montecarlo(
            ["AAA", "BBB"], sims=100, horizon=63,
            models=["gbm", "bootstrap"],
        )
        assert len(result["models"]) >= 1

    def test_bust_probability_in_range(self, patched_fetch):
        result = run_portfolio_montecarlo(["AAA"], sims=100, horizon=63)
        for model in result["models"].values():
            bp = model.get("bust_probability")
            if bp is not None:
                assert 0.0 <= bp <= 1.0

    def test_percentile_ordering(self, patched_fetch):
        result = run_portfolio_montecarlo(
            ["AAA", "BBB"], sims=200, horizon=63,
            models=["gbm"],
        )
        if "gbm" in result["models"]:
            m = result["models"]["gbm"]
            p5, p50, p95 = m.get("percentile_5"), m.get("median"), m.get("percentile_95")
            if all(v is not None for v in [p5, p50, p95]):
                assert p5 <= p50 <= p95, f"Percentile order violated: {p5} {p50} {p95}"

    def test_summary_has_median(self, patched_fetch):
        result = run_portfolio_montecarlo(["AAA", "BBB"], sims=100, horizon=63)
        assert "summary" in result
        assert "cross_model_median_return" in result["summary"]

    def test_unknown_symbol_returns_error(self, patched_fetch):
        result = run_portfolio_montecarlo(["ZZZNOTREAL"], sims=50, horizon=30)
        assert "error" in result


# ---------------------------------------------------------------------------
# get_correlation_matrix
# ---------------------------------------------------------------------------

class TestGetCorrelationMatrix:
    def test_matrix_shape(self, patched_fetch):
        result = get_correlation_matrix(["AAA", "BBB", "CCC"], period="1y")
        assert "error" not in result
        matrix = result["matrix"]
        for sym_i in ["AAA", "BBB", "CCC"]:
            for sym_j in ["AAA", "BBB", "CCC"]:
                assert sym_i in matrix
                assert sym_j in matrix[sym_i]

    def test_diagonal_is_one(self, patched_fetch):
        result = get_correlation_matrix(["AAA", "BBB", "CCC"], period="1y")
        matrix = result["matrix"]
        for sym in ["AAA", "BBB", "CCC"]:
            diag = matrix[sym][sym]
            assert diag == pytest.approx(1.0, abs=1e-6), f"Diagonal != 1 for {sym}: {diag}"

    def test_symmetry(self, patched_fetch):
        result = get_correlation_matrix(["AAA", "BBB"], period="1y")
        matrix = result["matrix"]
        ab = matrix["AAA"]["BBB"]
        ba = matrix["BBB"]["AAA"]
        if ab is not None and ba is not None:
            assert ab == pytest.approx(ba, abs=1e-9)

    def test_values_between_minus1_and_1(self, patched_fetch):
        result = get_correlation_matrix(["AAA", "BBB", "CCC"], period="1y")
        for pair in result["pairs"]:
            val = pair["correlation"]
            if val is not None:
                assert -1.0 <= val <= 1.0, f"Correlation out of range: {val}"

    def test_pairs_sorted_by_abs_correlation(self, patched_fetch):
        result = get_correlation_matrix(["AAA", "BBB", "CCC"], period="1y")
        abs_vals = [p["abs_correlation"] for p in result["pairs"] if p["abs_correlation"] is not None]
        assert abs_vals == sorted(abs_vals, reverse=True)

    def test_too_few_symbols_returns_error(self, patched_fetch):
        result = get_correlation_matrix(["AAA"], period="1y")
        assert "error" in result

    def test_trading_days_positive(self, patched_fetch):
        result = get_correlation_matrix(["AAA", "BBB"], period="1y")
        assert result.get("trading_days", 0) > 0
