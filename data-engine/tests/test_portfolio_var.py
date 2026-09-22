"""Historical VaR/CVaR surfacing in portfolio intelligence."""

from datetime import date, timedelta

import pytest

from app.services.portfolio_intelligence_service import PortfolioIntelligenceService


def _series(values: list[float]) -> dict[date, float]:
    start = date(2026, 1, 1)
    return {start + timedelta(days=i): value for i, value in enumerate(values)}


def test_historical_var_requires_minimum_history() -> None:
    var, cvar = PortfolioIntelligenceService._historical_var(_series([0.01] * 19))
    assert var is None and cvar is None


def test_historical_var_quantile_and_tail_mean() -> None:
    # 100 observations from -10% to +8.9% in 0.1% steps (ascending).
    values = [(-10 + i * 0.1) / 100 for i in range(100)]
    var, cvar = PortfolioIntelligenceService._historical_var(_series(values))
    # 95% VaR = 5th percentile observation (index 5) = -9.5%.
    assert var == pytest.approx(-0.095)
    # CVaR = mean of the worst 6 observations (-10% .. -9.5%).
    assert cvar == pytest.approx(sum(values[:6]) / 6)
    assert cvar < var  # expected shortfall is deeper than VaR


def test_historical_var_positive_series() -> None:
    values = [0.001 * i for i in range(30)]
    var, cvar = PortfolioIntelligenceService._historical_var(_series(values))
    assert var is not None and cvar is not None
    assert var >= 0  # no losses observed


def test_var_uses_sorted_returns_not_dates() -> None:
    # Same values, shuffled insertion order: result must be identical.
    import random

    values = [(-5 + i * 0.2) / 100 for i in range(60)]
    shuffled = values[:]
    random.Random(42).shuffle(shuffled)
    assert PortfolioIntelligenceService._historical_var(
        _series(values)
    ) == PortfolioIntelligenceService._historical_var(_series(shuffled))
