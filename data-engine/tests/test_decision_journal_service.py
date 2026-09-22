"""DecisionJournalService contract tests.

A decision journal is only useful if each entry freezes the exact context
the decision was taken in: the latest thesis, model and price at write
time - with explicit Nones when that context does not exist.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import (
    Base,
    Company,
    FundamentalModelVersion,
    MarketPrice,
    ThesisVersion,
)
from app.services.fundamental_review_service import DecisionJournalService


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


def test_entry_freezes_latest_context(db):
    company = _company(db)
    thesis = ThesisVersion(
        company_id=company.id, version=4, status="published",
        thesis_markdown="# t", executive_summary="e",
    )
    model = FundamentalModelVersion(
        company_id=company.id, version=2, engine_version="e1", algorithm_version="a1",
        framework_key="holding", horizon_years=5, status="completed",
        input_fingerprint="f" * 64, forecast_fingerprint="g" * 64,
        market_snapshot_fingerprint="h" * 64, valuation_snapshot_fingerprint="i" * 64,
    )
    price = MarketPrice(
        company_id=company.id, date=date(2026, 9, 22),
        open=Decimal("200"), high=Decimal("205"), low=Decimal("198"),
        close=Decimal("202"), adj_close=Decimal("202"), source="Finnhub",
    )
    db.add_all([thesis, model, price])
    db.commit()

    entry = DecisionJournalService().create(
        db, company, decision="buy", rationale="margin of safety",
        what_must_be_true=["services keeps growing", "buyback sustained"],
    )
    assert entry.thesis_version_id == thesis.id
    assert entry.model_version_id == model.id
    assert entry.price == Decimal("202")
    assert entry.metadata_["thesis_version"] == 4
    assert entry.metadata_["model_version"] == 2
    assert entry.what_must_be_true == ["services keeps growing", "buyback sustained"]


def test_entry_without_context_records_explicit_nones(db):
    company = _company(db)
    entry = DecisionJournalService().create(
        db, company, decision="watch", rationale="waiting for data",
        what_must_be_true=[],
    )
    assert entry.thesis_version_id is None
    assert entry.model_version_id is None
    assert entry.price is None
    assert entry.metadata_ == {"thesis_version": None, "model_version": None}


def test_list_orders_newest_first(db):
    company = _company(db)
    service = DecisionJournalService()
    service.create(db, company, decision="watch", rationale="first", what_must_be_true=[])
    service.create(db, company, decision="buy", rationale="second", what_must_be_true=[])
    entries = service.list(db, company)
    assert [e.rationale for e in entries] == ["second", "first"]
