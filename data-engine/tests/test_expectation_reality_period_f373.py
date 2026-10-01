"""F373: annual forecasts are only compared with annual actuals."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, FinancialFact
from app.services.fundamental_review_service import ExpectationRealityService
from tests.test_expectation_reality import _company, _fact, _forecast, _model

NOW = datetime.now(UTC)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _q4_fact(db, company, created_at):
    db.add(FinancialFact(
        company_id=company.id, metric="revenue", value=Decimal("300"), unit="USD",
        period="2026-12-31:Q4", fiscal_year=2026, fiscal_quarter="Q4", source_type="SEC",
        is_reported=True, confidence=Decimal("0.95"), created_at=created_at,
    ))
    db.commit()


def test_quarterly_actual_is_not_compared_with_annual_forecast(db):
    company = _company(db)
    model = _model(db, company, created_at=NOW - timedelta(days=30))
    _forecast(db, model, company, fiscal_year=2026, metric="revenue", value="1000")
    _q4_fact(db, company, NOW)
    review = ExpectationRealityService().review(db, company)[0]
    assert review.status == "pending_actual"
    assert review.actual_value is None


def test_annual_actual_wins_over_newer_quarterly_fact(db):
    company = _company(db)
    model = _model(db, company, created_at=NOW - timedelta(days=30))
    _forecast(db, model, company, fiscal_year=2026, metric="revenue", value="1000")
    _fact(db, company, metric="revenue", fiscal_year=2026, value="1000", created_at=NOW - timedelta(days=2))
    _q4_fact(db, company, NOW)
    review = ExpectationRealityService().review(db, company)[0]
    assert review.actual_value == Decimal("1000")
    assert review.status != "miss"
