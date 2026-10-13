"""Calendario unico de catalizadores: filtrado a cartera, orden y honestidad."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, Company, CorporateAction, Position
from app.services import catalyst_calendar_service as svc

D0, D1 = date(2026, 10, 14), date(2026, 10, 28)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _company(db, ticker, qty):
    company = Company(
        ticker=ticker, name=ticker, exchange="NASDAQ", currency="USD",
        sector="S", industry="I", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.commit()
    db.add(Position(company_id=company.id, quantity=Decimal(str(qty)), average_cost=1,
                    market_price=1, currency="USD"))
    db.commit()
    return company


def test_held_tickers_only_open_positions(db):
    _company(db, "aaa", 5)
    _company(db, "BBB", 0)
    assert svc.held_tickers(db) == {"AAA"}


def test_pending_actions_only_unapplied_in_range(db):
    c = _company(db, "AAA", 5)
    for eff, applied in ((date(2026, 10, 20), False), (date(2026, 10, 21), True),
                         (date(2026, 12, 1), False)):
        db.add(CorporateAction(company_id=c.id, action_type="split", effective_date=eff,
                               ratio=Decimal("2"), description="", applied=applied))
    db.commit()
    rows = svc.pending_actions(db, D0, D1)
    assert [r["effective_date"] for r in rows] == ["2026-10-20"]


def test_build_filters_to_portfolio_and_range_and_orders():
    events = svc.build_catalysts(
        held={"AAA", "KO"},
        desde=D0,
        hasta=D1,
        earnings=[
            {"symbol": "AAA", "date": "2026-10-22", "time": "after-market", "eps_forecast": 1.5},
            {"symbol": "ZZZ", "date": "2026-10-22", "time": None, "eps_forecast": None},
            {"symbol": "AAA", "date": "2026-11-30", "time": None, "eps_forecast": None},
        ],
        dividends=[
            {"symbol": "KO", "ex_date": "10/16/2026", "payment_date": "2026-10-30",
             "amount": 0.51},
            {"symbol": "KO", "ex_date": "N/A", "payment_date": None, "amount": None},
        ],
        actions=[{"ticker": "AAA", "action_type": "split", "effective_date": "2026-10-22",
                  "ratio": 2.0}],
    )
    assert [(e["date"], e["ticker"], e["type"]) for e in events] == [
        ("2026-10-16", "KO", "dividend_ex"),
        ("2026-10-22", "AAA", "earnings"),
        ("2026-10-22", "AAA", "corporate_action"),
    ]
    assert events[1]["detail"] == "tras el cierre, BPA estimado 1.50"
    assert events[0]["detail"] == "0.5100 por accion"
    assert all(e["source"] for e in events)


def test_no_invented_dates_when_source_has_none():
    events = svc.build_catalysts(
        held={"AAA"}, desde=D0, hasta=D1,
        earnings=[{"symbol": "AAA", "date": None}], dividends=[], actions=[],
    )
    assert events == []


def test_combine_status():
    assert svc.combine_status("ok", "ok") == "ok"
    assert svc.combine_status("ok", "partial") == "partial"
    assert svc.combine_status("unavailable", "unavailable") == "unavailable"
    assert svc.combine_status("ok", "unavailable") == "partial"
