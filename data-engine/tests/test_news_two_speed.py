"""Noticias a dos velocidades (decisión de Nico 2026-09-25):
carril tracked (cartera + watchlist) cada 30 min, universo en background."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, Company, Position, WatchItem
from app.workers.dramatiq_app import _tracked_companies


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _company(db: Session, ticker: str) -> Company:
    company = Company(
        ticker=ticker, name=f"{ticker} Inc.", exchange="", currency="USD",
        sector="Tech", industry="Tech", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[],
        factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


def test_tracked_includes_positions_and_watchlist_only(db):
    aapl = _company(db, "AAPL")
    _company(db, "MSFT")
    san = _company(db, "SAN")
    db.add(Position(company_id=aapl.id, tenant_id="tenant-test"))
    db.add(WatchItem(symbol="SAN.MC", tenant_id="tenant-test"))  # display ticker
    db.commit()
    tracked = {c.ticker for c in _tracked_companies(db)}
    assert tracked == {"AAPL", "SAN"}  # SAN.MC resuelve a SAN; MSFT fuera


def test_tracked_empty_is_empty_not_universe(db):
    _company(db, "AAPL")
    assert _tracked_companies(db) == []
