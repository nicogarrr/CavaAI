"""FundamentalModelRepository contract tests.

The repository is the reproducibility backbone of the fundamental
model: deterministic fingerprint scoping, tenant-gated persistence,
idempotent versioning by input fingerprint, and an honest round-trip
through latest_payload.
"""

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.models.entities import (
    Base,
    Company,
    FundamentalModelVersion,
    FundamentalValuationSnapshot,
)
from app.services.fundamental_model_repository import FundamentalModelRepository


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


def _payload(**overrides):
    payload = {
        "model_version": "e1",
        "algorithm_version": "a1",
        "framework": {"key": "quality_compounder"},
        "horizon_years": 5,
        "status": "final",
        "publishable": True,
        "assumptions": {"wacc": {"value": 0.09}},
        "scenarios": {
            "base": {
                "probability": 0.6,
                "assumptions": {},
                "forecast": {},
                "valuation": {"fair_value": 220},
            }
        },
        "current_price": 200,
        "market_opportunity": {
            "implied_by_valuation": {"share": 0.3},
            "market_share": 0.2,
        },
    }
    payload.update(overrides)
    return payload


def test_fingerprints_deterministic_and_scoped():
    repo = FundamentalModelRepository()
    base = repo.fingerprints(_payload())
    assert base == repo.fingerprints(_payload())  # deterministic

    changed_assumption = _payload()
    changed_assumption["assumptions"] = {"wacc": {"value": 0.10}}
    assert repo.fingerprints(changed_assumption)["input"] != base["input"]

    # Valuation-derived market fields are excluded from the INPUT fingerprint.
    changed_implied = _payload()
    changed_implied["market_opportunity"] = {
        "implied_by_valuation": {"share": 0.9},
        "market_share": 0.8,
    }
    assert repo.fingerprints(changed_implied)["input"] == base["input"]

    # Scenario valuations move the valuation fingerprint, not the input one.
    changed_valuation = _payload()
    changed_valuation["scenarios"] = {
        "base": {"probability": 0.6, "assumptions": {}, "forecast": {},
                 "valuation": {"fair_value": 999}}
    }
    scoped = repo.fingerprints(changed_valuation)
    assert scoped["input"] == base["input"]
    assert scoped["valuation"] != base["valuation"]


def test_persist_requires_tenant(db):
    db.info.pop("tenant_id")
    company = _company(db)
    assert FundamentalModelRepository().persist(db, company, _payload()) is None
    assert db.scalar(select(func.count()).select_from(FundamentalModelVersion)) == 0


def test_persist_idempotent_for_same_input(db):
    company = _company(db)
    repo = FundamentalModelRepository()
    first = repo.persist(db, company, _payload())
    second = repo.persist(db, company, _payload())
    assert first.id == second.id
    assert first.version == 1
    assert db.scalar(select(func.count()).select_from(FundamentalModelVersion)) == 1
    assert db.scalar(select(func.count()).select_from(FundamentalValuationSnapshot)) == 1


def test_changed_input_creates_next_version(db):
    company = _company(db)
    repo = FundamentalModelRepository()
    repo.persist(db, company, _payload())
    changed = _payload()
    changed["assumptions"] = {"wacc": {"value": 0.10}}
    model = repo.persist(db, company, changed)
    assert model.version == 2
    assert model.input_fingerprint == repo.fingerprint(changed)
    assert db.scalar(select(func.count()).select_from(FundamentalModelVersion)) == 2


def test_latest_payload_roundtrip(db):
    company = _company(db)
    repo = FundamentalModelRepository()
    assert repo.latest_payload(db, company) is None

    model = repo.persist(db, company, _payload())
    payload = repo.latest_payload(db, company)
    persistence = payload["persistence"]
    assert persistence["status"] == "persisted"
    assert persistence["version"] == model.version
    assert persistence["input_fingerprint"] == model.input_fingerprint
    # Valuation side composed back from the persisted snapshot.
    assert payload["current_price"] == 200
    assert payload["scenarios"]["base"]["valuation"] == {"fair_value": 220}
