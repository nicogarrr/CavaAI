from decimal import Decimal
from uuid import uuid4

from sqlalchemy import delete, select

from app.core.database import SessionLocal, init_db
from app.models import (
    Company,
    DecisionJournalEntry,
    ExpectationReview,
    FinancialFact,
    FundamentalAssumption,
    FundamentalDriver,
    FundamentalForecast,
    FundamentalModelVersion,
    Tenant,
)
from app.services.fundamental_review_service import (
    DecisionJournalService,
    ExpectationRealityService,
)
from app.services.long_term_model_service import LongTermModelService


def _fact(db, company_id: int, metric: str, value: float, year: int) -> FinancialFact:
    fact = FinancialFact(
        company_id=company_id,
        metric=metric,
        value=Decimal(str(value)),
        unit="shares" if metric == "shares_diluted" else "USD",
        period=f"FY{year}",
        fiscal_year=year,
        fiscal_quarter="FY",
        source_type="fundamental_persistence_test",
        is_reported=True,
        confidence=Decimal("0.90"),
    )
    db.add(fact)
    return fact


def test_model_versions_journal_and_expectation_reality_are_persisted():
    init_db()
    suffix = uuid4().hex[:8]
    db = SessionLocal()
    try:
        tenant = Tenant(external_id=f"fundamental-{suffix}", name="Fundamental test")
        company = Company(
            ticker=f"F{suffix[:5]}".upper(),
            name="Persisted Model Co",
            exchange="TEST",
            currency="USD",
            sector="Industrials",
            industry="Test",
            company_type="standard",
            valuation_model="standard_dcf",
            special_sources=[],
            special_risks=[],
            factor_tags=["quality"],
        )
        db.add_all([tenant, company])
        db.commit()
        company_id = company.id
        tenant_id = tenant.id
        db.info["tenant_id"] = tenant.id
        db.info["user_id"] = "analyst-test"

        for year, revenue, fcf, shares in (
            (2023, 100, 15, 10),
            (2024, 112, 18, 9.9),
            (2025, 126, 21, 9.8),
        ):
            _fact(db, company.id, "revenue", revenue, year)
            _fact(db, company.id, "free_cash_flow", fcf, year)
            _fact(db, company.id, "shares_diluted", shares, year)
            _fact(db, company.id, "market_size", 1000 + (year - 2023) * 100, year)
        db.commit()

        first = LongTermModelService().build(db, company, horizon=5)
        second = LongTermModelService().build(db, company, horizon=5)

        assert first["persistence"]["status"] == "persisted"
        assert first["persistence"]["model_version_id"] == second["persistence"]["model_version_id"]
        probabilities = [scenario["probability"] for scenario in first["scenarios"].values()]
        assert abs(sum(probabilities) - 1) < 1e-9
        assert probabilities != [0.25, 0.50, 0.25]
        model_id = first["persistence"]["model_version_id"]
        assert db.scalar(select(FundamentalDriver).where(FundamentalDriver.model_version_id == model_id))
        assert db.scalar(select(FundamentalAssumption).where(FundamentalAssumption.model_version_id == model_id))
        forecast = db.scalar(
            select(FundamentalForecast).where(
                FundamentalForecast.model_version_id == model_id,
                FundamentalForecast.scenario == "base",
                FundamentalForecast.metric == "revenue",
            )
        )
        assert forecast is not None

        entry = DecisionJournalService().create(
            db,
            company,
            decision="hold",
            rationale="Wait for the first forecast checkpoint.",
            what_must_be_true=["Revenue remains on plan"],
        )
        assert entry.model_version_id == model_id

        _fact(db, company.id, "revenue", float(forecast.value) * 0.8, forecast.fiscal_year)
        db.commit()
        reviews = ExpectationRealityService().review(db, company)
        matched = next(item for item in reviews if item.forecast_id == forecast.id)
        assert matched.status == "miss"
        assert matched.actual_fact_id is not None
    finally:
        db.rollback()
        db.info.pop("tenant_id", None)
        for model in (
            ExpectationReview,
            DecisionJournalEntry,
            FundamentalForecast,
            FundamentalAssumption,
            FundamentalDriver,
            FundamentalModelVersion,
            FinancialFact,
        ):
            db.execute(
                delete(model)
                .where(model.company_id == company_id)
                .execution_options(include_all_tenants=True)
            )
        db.execute(delete(Company).where(Company.id == company_id))
        db.execute(delete(Tenant).where(Tenant.id == tenant_id))
        db.commit()
        db.close()
