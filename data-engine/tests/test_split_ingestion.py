"""Split ingestion tests."""

import asyncio
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.entities import Base, Company, CorporateAction, Portfolio, Position
from app.services.split_ingestion_service import SplitIngestionService


class FakeFMP:
    def __init__(self, payload=None, error=None):
        self.payload = payload if payload is not None else []
        self.error = error

    async def splits(self, ticker: str):
        if self.error:
            raise self.error
        return self.payload


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _company(db: Session, ticker: str = "AAPL") -> Company:
    company = Company(
        ticker=ticker, name=ticker, exchange="NASDAQ", currency="USD",
        sector="Tech", industry="Tech", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


def _position(db: Session, company: Company) -> None:
    portfolio = Portfolio(name="p")
    db.add(portfolio)
    db.commit()
    db.add(Position(
        portfolio_id=portfolio.id, company_id=company.id, quantity=Decimal("10"),
        average_cost=Decimal("150"), market_price=Decimal("200"),
        market_value=Decimal("2000"), unrealized_pnl=Decimal("500"),
        realized_pnl=Decimal("0"), as_of=date.today(), currency="USD",
    ))
    db.commit()


SPLIT_PAYLOAD = [
    {"symbol": "AAPL", "date": "2020-08-31", "numerator": 4, "denominator": 1, "label": "4-for-1 split"},
    {"symbol": "AAPL", "date": "2014-06-09", "numerator": 7, "denominator": 1, "label": "7-for-1 split"},
]


def test_sync_inserts_unapplied_deduped_splits(db):
    service = SplitIngestionService(fmp=FakeFMP(payload=SPLIT_PAYLOAD * 2))
    _company(db)
    first = asyncio.run(service.sync_company(db, ticker="AAPL"))
    assert first["status"] == "ok"
    assert first["inserted"] == 2 and first["existing"] == 2
    second = asyncio.run(service.sync_company(db, ticker="AAPL"))
    assert second["inserted"] == 0 and second["existing"] == 4
    rows = db.scalars(select(CorporateAction)).all()
    assert len(rows) == 2
    assert all(not row.applied for row in rows)
    assert all(row.source == "fmp" and row.fetched_at is not None for row in rows)
    assert {row.action_type for row in rows} == {"split"}


def test_reverse_split_classification(db):
    payload = [{"symbol": "AAPL", "date": "2024-01-15", "numerator": 1, "denominator": 10}]
    service = SplitIngestionService(fmp=FakeFMP(payload=payload))
    _company(db)
    result = asyncio.run(service.sync_company(db, ticker="AAPL"))
    assert result["inserted"] == 1
    row = db.scalars(select(CorporateAction)).one()
    assert row.action_type == "reverse_split"
    assert row.ratio == Decimal("0.1")


def test_provider_failure_is_unavailable_not_fabricated(db):
    service = SplitIngestionService(fmp=FakeFMP(error=RuntimeError("403 Forbidden")))
    _company(db)
    result = asyncio.run(service.sync_company(db, ticker="AAPL"))
    assert result["status"] == "unavailable"
    assert db.scalars(select(CorporateAction)).all() == []


def test_malformed_rows_skipped(db):
    payload = [
        {"symbol": "AAPL", "date": "not-a-date", "numerator": 4, "denominator": 1},
        {"symbol": "AAPL", "date": "2020-08-31", "numerator": 0, "denominator": 1},
        {"symbol": "AAPL"},
    ]
    service = SplitIngestionService(fmp=FakeFMP(payload=payload))
    _company(db)
    result = asyncio.run(service.sync_company(db, ticker="AAPL"))
    assert result["inserted"] == 0
    assert db.scalars(select(CorporateAction)).all() == []


def test_sync_portfolio_provenance(db):
    company = _company(db)
    _position(db, company)
    service = SplitIngestionService(fmp=FakeFMP(payload=SPLIT_PAYLOAD))
    result = asyncio.run(service.sync_portfolio(db))
    assert result["synced"] == 1
    assert result["provenance"]["source_kind"] == "unofficial"
    assert result["provenance"]["coverage"] == "ok"
