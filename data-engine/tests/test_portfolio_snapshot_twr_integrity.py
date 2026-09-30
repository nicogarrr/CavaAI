"""TWR integrity: F362 (previous coverage/base), F378 (currency), F379 (gaps)."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, Company, PortfolioDailySnapshot, Position, Transaction
from app.services.portfolio_fx_service import PortfolioFXService
from app.services.portfolio_snapshot_service import PortfolioSnapshotService

D0 = date(2026, 9, 1)
D1 = D0 + timedelta(days=1)
D2 = D0 + timedelta(days=2)


@pytest.fixture
def setup():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.info["tenant_id"] = "tenant-test"
        company = Company(
            ticker="AAPL", name="Apple", exchange="NASDAQ", currency="USD",
            sector="Tech", industry="Tech", company_type="holding",
            valuation_model="unassigned", special_sources=[], special_risks=[],
            factor_tags=[],
        )
        db.add(company)
        db.commit()
        portfolio = PortfolioFXService().ensure_portfolio(db)
        position = Position(
            portfolio_id=portfolio.id, company_id=company.id, quantity=Decimal("10"),
            market_price=Decimal("100"), currency="EUR", as_of=D0,
        )
        db.add(position)
        db.commit()
        yield db, portfolio, position


def _snap(db, day, position, price):
    position.as_of = day
    position.market_price = Decimal(price)
    db.commit()
    return PortfolioSnapshotService().capture(db, as_of=day)


def test_partial_previous_coverage_gives_no_return(setup):
    db, portfolio, position = setup
    first = _snap(db, D0, position, "100")
    first.pricing_coverage = Decimal("0.5")
    db.commit()
    second = _snap(db, D1, position, "200")
    assert second.daily_return is None
    assert second.cumulative_twr is None


def test_broken_series_does_not_restart_from_zero(setup):
    db, portfolio, position = setup
    _snap(db, D0, position, "100")
    second = _snap(db, D1, position, "110")
    second.cumulative_twr = None
    second.daily_return = None
    db.commit()
    third = _snap(db, D2, position, "120")
    assert third.cumulative_twr is None


def test_previous_different_currency_gives_no_return(setup):
    db, portfolio, position = setup
    first = _snap(db, D0, position, "100")
    first.base_currency = "USD"
    db.commit()
    second = _snap(db, D1, position, "110")
    assert second.daily_return is None


def test_missing_intermediate_snapshot_discounts_all_interval_flows(setup):
    db, portfolio, position = setup
    _snap(db, D0, position, "100")  # total 1000
    # D1 has no snapshot; deposit happened on D1, capture on D2.
    db.add(
        Transaction(
            portfolio_id=portfolio.id, trade_date=D1, action="deposit",
            quantity=Decimal("1"), price=Decimal("500"), currency="EUR",
            external_id="dep-gap",
        )
    )
    db.commit()
    position.quantity = Decimal("15")
    third = _snap(db, D2, position, "100")  # total 1500
    assert third.net_external_flow_base == Decimal("500")
    assert third.daily_return == pytest.approx(Decimal("0"))
    assert db.query(PortfolioDailySnapshot).count() == 2
