"""F369: las aportaciones en otra divisa no se suman como si fueran base."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base
from app.services.investment_plan_service import InvestmentPlanService
from app.services.portfolio_fx_service import PortfolioFXService
from tests.test_investment_plan_service import _plan


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _setup(db):
    service = InvestmentPlanService()
    _plan(service, db, start_date=date(2026, 1, 1))
    PortfolioFXService().ensure_portfolio(db)
    db.commit()
    return service


def test_foreign_contribution_without_fx_is_not_counted_at_par(db):
    service = _setup(db)
    service.add_contribution(db, date_=date(2026, 2, 1), amount=Decimal("1000"), currency="USD")
    metrics = service.plan_metrics(db)
    assert metrics["actual_contributions_base"] is None
    assert metrics["gap_base"] is None
    assert metrics["on_track"] is None
    assert metrics["contributions_complete"] is False
    assert metrics["contributions_missing_fx"][0]["quote_currency"] == "USD"
    assert metrics["actual_contributions_converted_base"] == 0.0


def test_foreign_contribution_with_dated_fx_is_converted(db):
    service = _setup(db)
    PortfolioFXService().upsert_rate(
        db, base_currency="EUR", quote_currency="USD", rate=Decimal("0.9"),
        rate_date=date(2026, 2, 1), source="test",
    )
    service.add_contribution(db, date_=date(2026, 2, 1), amount=Decimal("1000"), currency="USD")
    service.add_contribution(db, date_=date(2026, 2, 2), amount=Decimal("100"), currency="EUR")
    metrics = service.plan_metrics(db)
    assert metrics["contributions_complete"] is True
    assert metrics["actual_contributions_base"] == pytest.approx(1000.0)


def test_more_than_500_contributions_are_all_counted(db):
    service = _setup(db)
    for i in range(520):
        service.add_contribution(
            db, date_=date(2026, 2, 1), amount=Decimal("1"), currency="EUR", external_id=f"c{i}"
        )
    assert service.plan_metrics(db)["actual_contributions_base"] == pytest.approx(520.0)
