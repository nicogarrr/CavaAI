"""DriverAssumptionService contract tests.

Driver assumptions are the user's editable levers on the fundamental
model: versions must chain, unknown drivers must fail loudly, and the
active-override view must resolve to the latest version per cell.
"""

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import (
    Base,
    Company,
    DriverAssumptionVersion,
    FundamentalDriver,
    FundamentalModelVersion,
)
from app.services.driver_assumption_service import DriverAssumptionService


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


_model_version_seq = {"n": 0}


def _driver(db: Session, company: Company, key: str = "revenue_growth") -> FundamentalDriver:
    _model_version_seq["n"] += 1
    model = FundamentalModelVersion(
        company_id=company.id, version=_model_version_seq["n"], engine_version="e1", algorithm_version="a1",
        framework_key="holding", horizon_years=5, status="completed",
        input_fingerprint=("f" * 63) + key[-1], forecast_fingerprint="g" * 64,
        market_snapshot_fingerprint="h" * 64, valuation_snapshot_fingerprint="i" * 64,
    )
    db.add(model)
    db.flush()
    driver = FundamentalDriver(
        model_version_id=model.id, company_id=company.id,
        driver_key=key, driver_type="growth", status="estimated",
    )
    db.add(driver)
    db.commit()
    return driver


def _create(service, db, company, **overrides):
    args = {
        "driver_key": "revenue_growth",
        "fiscal_year": 2026,
        "scenario": "base",
        "value": Decimal("0.08"),
        "source": "user",
        "user_override": True,
        "confidence": Decimal("0.7"),
        "rationale": "services momentum",
    }
    args.update(overrides)
    return service.create(db, company, **args)


def test_create_unknown_driver_fails_loudly(db):
    company = _company(db)
    with pytest.raises(ValueError, match="does not exist"):
        _create(DriverAssumptionService(), db, company)


def test_versions_chain_through_previous_version_id(db):
    company = _company(db)
    _driver(db, company)
    service = DriverAssumptionService()
    v1 = _create(service, db, company)
    v2 = _create(service, db, company, value=Decimal("0.10"), rationale="raised guidance")
    assert v1.previous_version_id is None
    assert v2.previous_version_id == v1.id
    assert db.query(DriverAssumptionVersion).count() == 2


def test_active_overrides_resolve_to_latest_version_per_cell(db):
    company = _company(db)
    _driver(db, company)
    service = DriverAssumptionService()
    _create(service, db, company)
    v2 = _create(service, db, company, value=Decimal("0.10"), rationale="raised guidance")
    _create(service, db, company, scenario="bear", value=Decimal("0.03"))

    overrides = service.active_overrides(db, company)
    cell = overrides["revenue_growth"][2026]
    assert cell["base"]["version_id"] == v2.id  # latest wins
    assert cell["base"]["value"] == pytest.approx(0.10)
    assert cell["base"]["previous_version_id"] == v2.previous_version_id
    assert cell["bear"]["value"] == pytest.approx(0.03)


def test_list_filters_by_driver_and_scenario(db):
    company = _company(db)
    _driver(db, company)
    _driver(db, company, key="fcf_margin")
    service = DriverAssumptionService()
    _create(service, db, company)
    _create(service, db, company, driver_key="fcf_margin", value=Decimal("0.25"))
    _create(service, db, company, scenario="bear", value=Decimal("0.03"))

    assert len(service.list(db, company)) == 3
    assert len(service.list(db, company, driver_key="fcf_margin")) == 1
    assert len(service.list(db, company, scenario="bear")) == 1
