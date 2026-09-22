"""Issuer-domicile country exposure tests."""

from types import SimpleNamespace

from app.services.portfolio_intelligence_service import PortfolioIntelligenceService


def _row(exchange: str, domicile: str | None, value: float) -> tuple:
    position = SimpleNamespace(market_value_base=value, currency="USD")
    company = SimpleNamespace(
        exchange=exchange,
        domicile_country=domicile,
        sector="Tech",
        factor_tags=[],
    )
    return position, company


def test_domicile_preferred_over_exchange_map() -> None:
    # A US-listed (NYSE) ADR of a Dutch issuer counts as Netherlands.
    rows = [_row("NYSE", "Netherlands", 100.0)]
    exposures = PortfolioIntelligenceService._exposures(rows, 100.0)
    assert exposures["countries"] == {"Netherlands": 1.0}


def test_exchange_map_used_when_domicile_missing() -> None:
    rows = [_row("XETRA", None, 100.0)]
    exposures = PortfolioIntelligenceService._exposures(rows, 100.0)
    assert exposures["countries"] == {"Germany": 1.0}


def test_unknown_when_neither_domicile_nor_exchange_known() -> None:
    rows = [_row("SOME_OBSCURE_VENUE", None, 100.0)]
    exposures = PortfolioIntelligenceService._exposures(rows, 100.0)
    assert exposures["countries"] == {"Unknown": 1.0}


def test_mixed_domicile_and_exchange_fallback() -> None:
    rows = [
        _row("NASDAQ", None, 60.0),
        _row("LSE", "United Kingdom", 40.0),
    ]
    exposures = PortfolioIntelligenceService._exposures(rows, 100.0)
    assert exposures["countries"] == {"United States": 0.6, "United Kingdom": 0.4}
