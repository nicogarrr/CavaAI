"""F368: posiciones sin valor base no se descartan en silencio ni sostienen sugerencias."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, CashBalance, Company, Position
from app.services.investment_plan_service import InvestmentPlanService
from tests.test_investment_plan_service import _plan


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _company(ticker, sector="Tech"):
    return Company(
        ticker=ticker, name=ticker, exchange="NASDAQ", currency="USD",
        sector=sector, industry=sector, company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )


def test_unpriced_position_is_reported_and_suggestions_are_blocked(db):
    service = InvestmentPlanService()
    _plan(
        service, db,
        target_allocations=[
            {"kind": "sector", "label": "Tech", "target_pct": 60, "band_pct": 5},
            {"kind": "asset_class", "label": "Cash", "target_pct": 40, "band_pct": 5},
        ],
    )
    priced, unpriced = _company("AAPL"), _company("MSFT")
    db.add_all([priced, unpriced])
    db.flush()
    db.add(Position(company_id=priced.id, quantity=Decimal("10"), market_price=Decimal("100"),
                    currency="EUR", market_value_base=Decimal("1000"), as_of=date(2026, 9, 20)))
    db.add(Position(company_id=unpriced.id, quantity=Decimal("10"), market_price=Decimal("100"),
                    currency="USD", market_value_base=None, as_of=date(2026, 9, 20)))
    db.add(CashBalance(currency="EUR", balance=Decimal("1000"), as_of=date(2026, 9, 20)))
    db.commit()

    drift = service.drift_analysis(db)
    assert drift["status"] == "incomplete_fx"
    assert [m["ticker"] for m in drift["missing_fx"] if m["kind"] == "position"] == ["MSFT"]
    assert drift["suggestions"] == []
    assert drift["suggestions_blocked"] is True


def test_complete_coverage_keeps_suggestions(db):
    service = InvestmentPlanService()
    _plan(
        service, db,
        target_allocations=[{"kind": "asset_class", "label": "Cash", "target_pct": 40, "band_pct": 5}],
    )
    company = _company("AAPL")
    db.add(company)
    db.flush()
    db.add(Position(company_id=company.id, quantity=Decimal("10"), market_price=Decimal("100"),
                    currency="EUR", market_value_base=Decimal("1000"), as_of=date(2026, 9, 20)))
    db.add(CashBalance(currency="EUR", balance=Decimal("1000"), as_of=date(2026, 9, 20)))
    db.commit()
    drift = service.drift_analysis(db)
    assert drift["suggestions_blocked"] is False
    assert drift["suggestions"]
