"""ExpectationRealityService + MetricSemanticsRegistry contract tests.

Expectation-vs-reality review keeps forecasts honest: only models created
BEFORE the actual was known count as forecasts, classification follows
metric semantics (direction + tolerance), and missing actuals stay
explicitly pending.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.models.entities import (
    Base,
    Company,
    ExpectationReview,
    FinancialFact,
    FundamentalForecast,
    FundamentalModelVersion,
)
from app.services.fundamental_review_service import ExpectationRealityService
from app.services.metric_semantics import MetricSemanticsRegistry


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _company(db: Session) -> Company:
    company = Company(
        ticker="AAPL", name="Apple", exchange="NASDAQ", currency="USD",
        sector="Tech", industry="Tech", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


def _model(db: Session, company: Company, *, created_at: datetime) -> FundamentalModelVersion:
    model = FundamentalModelVersion(
        company_id=company.id, version=1, engine_version="e1", algorithm_version="a1",
        framework_key="holding", horizon_years=5, status="completed",
        input_fingerprint="f" * 64, forecast_fingerprint="g" * 64,
        market_snapshot_fingerprint="h" * 64, valuation_snapshot_fingerprint="i" * 64,
        created_at=created_at,
    )
    db.add(model)
    db.commit()
    return model


def _forecast(db: Session, model: FundamentalModelVersion, company: Company,
              *, fiscal_year: int, metric: str, value: str) -> FundamentalForecast:
    forecast = FundamentalForecast(
        model_version_id=model.id, company_id=company.id, scenario="base",
        probability=Decimal("0.55"), fiscal_year=fiscal_year, metric=metric,
        value=Decimal(value),
    )
    db.add(forecast)
    db.commit()
    return forecast


def _fact(db: Session, company: Company, *, metric: str, fiscal_year: int,
          value: str, created_at: datetime) -> FinancialFact:
    fact = FinancialFact(
        company_id=company.id, metric=metric, value=Decimal(value), unit="USD",
        period=f"{fiscal_year}:FY", fiscal_year=fiscal_year, source_type="SEC",
        is_reported=True, confidence=Decimal("0.95"), created_at=created_at,
    )
    db.add(fact)
    db.commit()
    return fact


NOW = datetime.now(UTC)


def test_review_classifies_beat_miss_met_by_semantics(db):
    company = _company(db)
    model = _model(db, company, created_at=NOW - timedelta(days=30))
    _forecast(db, model, company, fiscal_year=2025, metric="revenue", value="100")
    _forecast(db, model, company, fiscal_year=2025, metric="net_debt", value="50")
    # revenue +10% (tolerance 5%) -> beat; net_debt -10% (lower is better) -> beat
    _fact(db, company, metric="revenue", fiscal_year=2025, value="110", created_at=NOW)
    _fact(db, company, metric="net_debt", fiscal_year=2025, value="45", created_at=NOW)

    reviews = {r.metric: r for r in ExpectationRealityService().review(db, company)}
    assert reviews["revenue"].status == "beat"
    assert reviews["revenue"].variance_percent == pytest.approx(Decimal("0.1"))
    assert reviews["revenue"].semantics == "higher_is_better"
    assert reviews["revenue"].actual_source_type == "financial_fact"
    assert reviews["revenue"].actual_fact_id is not None
    assert reviews["net_debt"].status == "beat"
    assert reviews["net_debt"].semantics == "lower_is_better"
    assert reviews["revenue"].trace["selection_policy"] == "latest model created before actual"


def test_model_created_after_actual_is_not_a_forecast(db):
    company = _company(db)
    # Actual known first; model built afterwards -> hindsight, not a forecast.
    _fact(db, company, metric="revenue", fiscal_year=2025, value="110",
          created_at=NOW - timedelta(days=10))
    model = _model(db, company, created_at=NOW)
    _forecast(db, model, company, fiscal_year=2025, metric="revenue", value="100")

    reviews = ExpectationRealityService().review(db, company)
    assert reviews == []
    assert db.scalar(select(func.count()).select_from(ExpectationReview)) == 0


def test_missing_actual_stays_pending_with_cleared_fields(db):
    company = _company(db)
    model = _model(db, company, created_at=NOW - timedelta(days=30))
    _forecast(db, model, company, fiscal_year=2027, metric="revenue", value="100")

    reviews = ExpectationRealityService().review(db, company)
    assert len(reviews) == 1
    review = reviews[0]
    assert review.status == "pending_actual"
    assert review.actual_value is None
    assert review.variance is None
    assert review.actual_source_type is None


def test_review_is_idempotent_and_updates_in_place(db):
    company = _company(db)
    model = _model(db, company, created_at=NOW - timedelta(days=30))
    _forecast(db, model, company, fiscal_year=2025, metric="revenue", value="100")
    _fact(db, company, metric="revenue", fiscal_year=2025, value="103", created_at=NOW)

    service = ExpectationRealityService()
    first = service.review(db, company)
    second = service.review(db, company)
    assert db.scalar(select(func.count()).select_from(ExpectationReview)) == 1
    assert first[0].id == second[0].id
    # +3% within the 5% revenue tolerance -> met
    assert second[0].status == "met"


# -- semantics registry (pure) ---------------------------------------------------

def test_semantics_classify_matrix():
    reg = MetricSemanticsRegistry
    assert reg.classify("revenue", Decimal("100"), Decimal("110"))[0] == "beat"
    assert reg.classify("revenue", Decimal("100"), Decimal("103"))[0] == "met"
    assert reg.classify("revenue", Decimal("100"), Decimal("90"))[0] == "miss"
    assert reg.classify("net_debt", Decimal("100"), Decimal("90"))[0] == "beat"
    assert reg.classify("net_debt", Decimal("100"), Decimal("110"))[0] == "miss"
    assert reg.classify("capital_expenditure", Decimal("100"), Decimal("120"))[0] == "outside_tolerance"
    status, pct = reg.classify("revenue", Decimal("0"), Decimal("50"))
    assert status == "met" and pct is None
    # Unknown metrics fall back to context_dependent with 5% tolerance.
    assert reg.get("brand_new_metric").direction == "context_dependent"
