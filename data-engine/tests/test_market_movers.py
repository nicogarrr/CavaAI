"""Contratos de GET /api/market/movers: frío-seguro y matemática honesta.

El endpoint nunca asume caché caliente: sin filas devuelve universo vacío
(la UI lo muestra como estado honesto) en lugar de KeyError/500.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.routes.market import market_movers
from app.models.entities import Base, Company, MarketPrice


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    with factory() as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _company(db: Session, ticker: str) -> Company:
    company = Company(
        ticker=ticker, name=ticker, exchange="NASDAQ", currency="USD",
        sector="S", industry="I", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[],
        factor_tags=[],
    )
    db.add(company)
    db.flush()
    return company


def _price(db: Session, company: Company, day: date, close: str, volume: int = 100) -> None:
    db.add(MarketPrice(
        company_id=company.id, date=day, open=Decimal(close),
        high=Decimal(close), low=Decimal(close), close=Decimal(close),
        adj_close=Decimal(close), volume=volume, source="test",
    ))
    db.flush()


def test_cold_start_returns_empty_universe_without_errors(db: Session):
    out = market_movers(db, 10)
    assert out["universe"] == 0
    assert out["as_of"] is None
    assert out["gainers"] == [] and out["losers"] == [] and out["most_active"] == []


def test_change_math_and_sorting(db: Session):
    aaa = _company(db, "AAA")  # +10%
    _price(db, aaa, date(2026, 9, 21), "100", volume=10)
    _price(db, aaa, date(2026, 9, 22), "110", volume=10)
    bbb = _company(db, "BBB")  # -20%, más activa
    _price(db, bbb, date(2026, 9, 21), "100", volume=999)
    _price(db, bbb, date(2026, 9, 22), "80", volume=999)
    ccc = _company(db, "CCC")  # +5%
    _price(db, ccc, date(2026, 9, 21), "100", volume=5)
    _price(db, ccc, date(2026, 9, 22), "105", volume=5)

    out = market_movers(db, 10)
    assert out["universe"] == 3
    assert out["as_of"] == "2026-09-22"
    assert [m["ticker"] for m in out["gainers"]] == ["AAA", "CCC", "BBB"]
    assert out["gainers"][0]["change_pct"] == pytest.approx(10.0)
    assert [m["ticker"] for m in out["losers"]] == ["BBB", "CCC", "AAA"]
    assert out["losers"][0]["change_pct"] == pytest.approx(-20.0)
    assert out["most_active"][0]["ticker"] == "BBB"


def test_single_price_row_does_not_crash_and_counts_zero_change(db: Session):
    solo = _company(db, "SOLO")
    _price(db, solo, date(2026, 9, 22), "50", volume=7)
    out = market_movers(db, 10)
    assert out["universe"] == 1
    assert out["gainers"][0]["ticker"] == "SOLO"
    assert out["gainers"][0]["change_pct"] == 0.0


def test_limit_slices_lists(db: Session):
    for i in range(5):
        company = _company(db, f"L{i:02d}")
        _price(db, company, date(2026, 9, 21), "100")
        _price(db, company, date(2026, 9, 22), str(100 + i))
    out = market_movers(db, 2)
    assert len(out["gainers"]) == 2 and len(out["losers"]) == 2 and len(out["most_active"]) == 2
    assert out["universe"] == 5
