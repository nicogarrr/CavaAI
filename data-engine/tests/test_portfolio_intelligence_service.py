"""PortfolioIntelligenceService honesty contracts.

A position without a base-currency value (missing FX) must never be silently
counted as zero in totals, weights or exposures - it is excluded and reported
in missing_fx. A zero would understate concentration and distort exposures
without any visible signal.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, Company, Portfolio, Position
from app.services.portfolio_intelligence_service import PortfolioIntelligenceService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _company(db: Session, ticker: str, currency: str = "USD") -> Company:
    company = Company(
        ticker=ticker, name=ticker, exchange="NASDAQ", currency=currency,
        sector="Tech", industry="I", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


def _position(db, company, *, currency, market_value_base, market_value="1000"):
    position = Position(
        company_id=company.id,
        quantity=Decimal("10"),
        currency=currency,
        market_value=Decimal(market_value),
        market_value_base=(
            None if market_value_base is None else Decimal(str(market_value_base))
        ),
        as_of=date(2026, 9, 20),
    )
    db.add(position)
    db.commit()
    return position


def _eur_portfolio(db):
    db.add(Portfolio(name="Main", base_currency="EUR", is_default=True))
    db.commit()


def test_position_without_base_value_is_reported_not_zeroed(db):
    _eur_portfolio(db)
    usd = _company(db, "AAA", currency="USD")
    eur = _company(db, "BBB", currency="EUR")
    # No EUR value available for AAA (missing FX upstream).
    _position(db, usd, currency="USD", market_value_base=None)
    _position(db, eur, currency="EUR", market_value_base="500")

    result = PortfolioIntelligenceService().build(db)

    missing = result["missing_fx"]
    assert [item["ticker"] for item in missing] == ["AAA"]
    assert missing[0]["quote_currency"] == "USD"
    assert missing[0]["base_currency"] == "EUR"
    # AAA is excluded, not zero-weighted: BBB carries 100% of the valued book.
    assert result["concentration"]["weights"] == {"BBB": 1.0}
    assert result["concentration"]["top_1"] == 1.0
    assert result["exposures"]["currencies"] == {"EUR": 1.0}
    assert any("missing FX" in note for note in result["coverage"]["limitations"])


def test_base_currency_fallback_uses_native_value(db):
    _eur_portfolio(db)
    eur = _company(db, "CCC", currency="EUR")
    # market_value_base missing but the position is already in base currency:
    # the native value is an honest fallback, no missing_fx entry.
    _position(db, eur, currency="EUR", market_value_base=None, market_value="750")

    result = PortfolioIntelligenceService().build(db)

    assert result["missing_fx"] == []
    assert result["concentration"]["weights"] == {"CCC": 1.0}
    assert result["exposures"]["currencies"] == {"EUR": 1.0}
