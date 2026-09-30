"""F376 audit: _series_change must ignore quarterly rows and compare full years only."""
from decimal import Decimal
from types import SimpleNamespace

from app.services.portfolio_intelligence_service import PortfolioIntelligenceService


def _row(year, value, quarter=None):
    return SimpleNamespace(fiscal_year=year, fiscal_quarter=quarter, value=Decimal(str(value)))


def test_mixed_annual_and_quarterly_eps_compares_full_years_only():
    series = [_row(2023, 10), _row(2024, 12), _row(2025, 3, "Q1")]
    assert round(PortfolioIntelligenceService._series_change(series), 6) == 0.2


def test_only_quarterly_rows_gives_no_change():
    assert PortfolioIntelligenceService._series_change([_row(2024, 3, "Q1"), _row(2025, 4, "Q1")]) is None


def test_unordered_annual_rows_and_duplicates():
    series = [_row(2024, 12), _row(2023, 10), _row(2024, 99)]
    assert round(PortfolioIntelligenceService._series_change(series), 6) == 0.2
