"""RiskService.dashboard contract tests.

The portfolio risk snapshot must convert everything to base currency
point-in-time, exclude - never guess - rows without an FX rate, and say
so through status, provenance and the missing_fx ledger.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, CashBalance, Company, Position
from app.services.risk_service import RiskService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _company(db: Session, ticker: str) -> Company:
    company = Company(
        ticker=ticker, name=f"{ticker} Co", exchange="XETRA", currency="EUR",
        sector="Tech", industry="Tech", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


def test_base_currency_position_and_cash_valued_without_fx(db):
    company = _company(db, "SAN")
    db.add(
        Position(
            company_id=company.id, quantity=Decimal("10"), market_price=Decimal("100"),
            currency="EUR", market_value_native=Decimal("1000"), market_value_base=None,
            as_of=date(2026, 9, 20),
        )
    )
    db.add(CashBalance(currency="EUR", balance=Decimal("500"), as_of=date(2026, 9, 21)))
    db.commit()

    result = RiskService().dashboard(db)
    assert result["status"] == "ok"
    assert result["base_currency"] == "EUR"
    assert result["missing_fx"] == []
    assert result["cash_native"] == {"EUR": 500.0}
    assert result["total_value"] == pytest.approx(1500.0)
    assert result["data_as_of"] == "2026-09-20"
    assert result["provenance"]["coverage"] == "ok"
    assert result["trace"]["excluded_for_missing_fx"] == 0


def test_position_without_base_value_excluded_and_reported(db):
    company = _company(db, "AAPL")
    db.add(
        Position(
            company_id=company.id, quantity=Decimal("5"), market_price=Decimal("200"),
            currency="USD", market_value=Decimal("1000"), market_value_base=None,
            as_of=date(2026, 9, 20),
        )
    )
    db.commit()

    result = RiskService().dashboard(db)
    assert result["status"] == "incomplete_fx"
    assert result["missing_fx"] == [
        {
            "kind": "position",
            "ticker": "AAPL",
            "quote_currency": "USD",
            "base_currency": "EUR",
            "as_of": "2026-09-20",
        }
    ]
    assert result["total_value"] == 0.0  # excluded, never guessed
    assert result["provenance"]["coverage"] == "partial"
    assert result["trace"]["excluded_for_missing_fx"] == 1
    assert result["trace"]["fx_policy"].startswith("quote amount multiplied by latest rate on or before")


def test_cash_without_fx_rate_excluded_and_reported(db):
    db.add(CashBalance(currency="USD", balance=Decimal("800"), as_of=date(2026, 9, 20)))
    db.add(CashBalance(currency="EUR", balance=Decimal("200"), as_of=date(2026, 9, 20)))
    db.commit()

    result = RiskService().dashboard(db)
    assert result["status"] == "incomplete_fx"
    cash_missing = [m for m in result["missing_fx"] if m["kind"] == "cash"]
    assert cash_missing == [
        {
            "kind": "cash",
            "quote_currency": "USD",
            "base_currency": "EUR",
            "as_of": "2026-09-20",
        }
    ]
    # USD cash kept out of the base total; EUR cash counted at par.
    assert result["cash_native"] == {"USD": 800.0, "EUR": 200.0}
    assert result["total_value"] == pytest.approx(200.0)
