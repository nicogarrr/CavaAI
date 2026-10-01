"""net_debt derivado de total_debt y cash_and_equivalents (mismo instante y unidad)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base as CoreBase  # noqa: F401
from app.models.entities import Base, Company, FinancialFact
from app.valuation.financial_snapshot import FinancialSnapshotBuilder


@pytest.fixture()
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.info["tenant_id"] = 1
        yield s
    eng.dispose()


def _company(db):
    c = Company(ticker="DND", name="Dnd", exchange="NASDAQ", company_type="growth",
                valuation_model="pre_revenue", factor_tags=[])
    db.add(c)
    db.commit()
    return c


def _fact(db, c, metric, value, period="2026-06-30:Q2", unit="USD"):
    f = FinancialFact(company_id=c.id, metric=metric, value=Decimal(str(value)), unit=unit,
                      period=period, fiscal_year=2026, fiscal_quarter="Q2", source_type="SEC")
    db.add(f)
    db.commit()
    return f


def test_net_debt_derived_from_debt_and_cash(db):
    c = _company(db)
    _fact(db, c, "revenue", 70_918_000)
    _fact(db, c, "shares_diluted", 255_982_592)
    debt = _fact(db, c, "total_debt", 1_000_000_000)
    cash = _fact(db, c, "cash_and_equivalents", 400_000_000)
    snap = FinancialSnapshotBuilder().build(db, c)
    assert snap.value("net_debt") == 600_000_000.0
    assert snap.derived["net_debt"] == [debt.id, cash.id]
    assert "net_debt" not in snap.missing_inputs
    assert snap.facts["net_debt"].source_type == "DERIVED"
    assert snap.facts["net_debt"] not in db  # transient, never persisted


def test_reported_net_debt_wins_over_derivation(db):
    c = _company(db)
    _fact(db, c, "revenue", 1_000)
    _fact(db, c, "shares_diluted", 10)
    _fact(db, c, "net_debt", 5)
    _fact(db, c, "total_debt", 100)
    _fact(db, c, "cash_and_equivalents", 40)
    snap = FinancialSnapshotBuilder().build(db, c)
    assert snap.value("net_debt") == 5.0
    assert "net_debt" not in snap.derived


def test_no_derivation_when_one_input_missing_or_period_differs(db):
    c = _company(db)
    _fact(db, c, "revenue", 1_000)
    _fact(db, c, "shares_diluted", 10)
    _fact(db, c, "total_debt", 100)
    snap = FinancialSnapshotBuilder().build(db, c)
    assert snap.value("net_debt") is None
    assert "net_debt" in snap.missing_inputs
    _fact(db, c, "cash_and_equivalents", 40, period="2025-12-31:FY")
    snap = FinancialSnapshotBuilder().build(db, c)
    assert snap.value("net_debt") is None
