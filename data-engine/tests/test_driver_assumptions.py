from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import (
    Company,
    FinancialFact,
    FundamentalDriver,
    FundamentalModelVersion,
    Tenant,
)
from app.services.company_framework import resolve_company_framework
from app.services.driver_assumption_service import DriverAssumptionService
from app.services.driver_operating_model import DriverOperatingModel


def test_driver_assumptions_are_versioned_and_override_only_the_selected_year():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        tenant = Tenant(external_id="driver-test", name="Driver test")
        db.add(tenant)
        db.flush()
        db.info["tenant_id"] = tenant.id
        company = Company(
            ticker="DRV",
            name="Driver Co",
            exchange="TEST",
            currency="USD",
            sector="Test",
            industry="Test",
            company_type="standard",
            valuation_model="standard_dcf",
            special_sources=[],
            special_risks=[],
            factor_tags=[],
        )
        db.add(company)
        db.flush()
        model = FundamentalModelVersion(
            company_id=company.id,
            version=1,
            engine_version="test",
            algorithm_version="test",
            framework_key="generic_fcf",
            horizon_years=5,
            status="ok",
            publishable=False,
            input_fingerprint="a" * 64,
            forecast_fingerprint="b" * 64,
            market_snapshot_fingerprint="c" * 64,
            valuation_snapshot_fingerprint="d" * 64,
        )
        db.add(model)
        db.flush()
        driver = FundamentalDriver(
            model_version_id=model.id,
            company_id=company.id,
            driver_key="revenue",
            driver_type="revenue_driver",
            required=True,
            status="sourced",
            value=Decimal("100"),
            unit="USD",
            currency="USD",
            time_basis="per_year",
            period="FY2025",
            source="filing",
            confidence=Decimal("0.9"),
        )
        db.add(driver)
        db.flush()
        service = DriverAssumptionService()
        first = service.create(
            db,
            company,
            driver_key="revenue",
            fiscal_year=2027,
            scenario="base",
            value=Decimal("400"),
            source="analyst",
            user_override=True,
            confidence=Decimal("0.8"),
            rationale="Initial explicit plan",
        )
        second = service.create(
            db,
            company,
            driver_key="revenue",
            fiscal_year=2027,
            scenario="base",
            value=Decimal("500"),
            source="analyst",
            user_override=True,
            confidence=Decimal("0.9"),
            rationale="Updated deployment schedule",
        )

        assert second.previous_version_id == first.id
        overrides = service.active_overrides(db, company)
        assert overrides["revenue"][2027]["base"]["value"] == 500
        fact = FinancialFact(
            id=1,
            company_id=company.id,
            metric="revenue",
            value=Decimal("100"),
            unit="USD",
            period="FY2025",
            fiscal_year=2025,
            fiscal_quarter="FY",
            source_type="filing",
            confidence=Decimal("0.9"),
        )
        result = DriverOperatingModel().build(
            resolve_company_framework(company),
            {"revenue": [fact]},
            latest_year=2025,
            horizon=2,
            scenario="base",
            assumption_overrides=overrides,
        )

        assert result["years"][0]["output"] == 100
        assert result["years"][1]["output"] == 500
        assumption = result["driver_forecasts"]["revenue"][1]["assumption"]
        assert assumption["method"] == "versioned_driver_override"
        assert assumption["version_id"] == second.id
        assert assumption["rationale"] == "Updated deployment schedule"
