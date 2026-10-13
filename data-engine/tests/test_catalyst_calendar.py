"""Calendario unico de catalizadores: formatos REALES de NASDAQ, cartera US y honestidad.

Las filas de NASDAQ usadas aqui replican lo medido en la API real: consenso
negativo entre parentesis ("($0.05)"), franjas "time-pre-market" /
"time-after-hours" / "time-not-supplied" y dividendos devueltos solo el dia de
su fecha ex.
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models.entities import Base, Company, CorporateAction, Position
from app.services import catalyst_calendar_service as svc
from app.services.connectors import earnings_calendar as connector

D0, D1 = date(2026, 10, 14), date(2026, 10, 28)


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db(engine):
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _company(db, ticker, qty, *, exchange="NASDAQ", currency="USD"):
    company = Company(
        ticker=ticker, name=ticker, exchange=exchange, currency=currency,
        sector="S", industry="I", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.commit()
    db.add(Position(company_id=company.id, quantity=Decimal(str(qty)), average_cost=1,
                    market_price=1, currency=currency))
    db.commit()
    return company


def test_parse_float_negative_in_parentheses():
    assert connector._parse_float("($0.05)") == pytest.approx(-0.05)
    assert connector._parse_float("$2.95") == pytest.approx(2.95)
    assert connector._parse_float("220,000,000,000") == pytest.approx(2.2e11)
    assert connector._parse_float("N/A") is None


def test_held_tickers_split_all_vs_us_only(db):
    _company(db, "aaa", 5)
    _company(db, "BBB", 0)
    _company(db, "ALM", 3, exchange="BME", currency="EUR")
    todos, solo_us = svc.held_tickers(db)
    assert todos == {"AAA", "ALM"}
    assert solo_us == {"AAA"}


def test_pending_actions_only_unapplied_in_range(db):
    c = _company(db, "AAA", 5)
    for eff, applied in ((date(2026, 10, 20), False), (date(2026, 10, 21), True),
                         (date(2026, 12, 1), False)):
        db.add(CorporateAction(company_id=c.id, action_type="split", effective_date=eff,
                               ratio=Decimal("2"), description="", applied=applied))
    db.commit()
    rows = svc.pending_actions(db, D0, D1)
    assert [r["effective_date"] for r in rows] == ["2026-10-20"]


def test_build_real_nasdaq_formats_and_us_only():
    events = svc.build_catalysts(
        held={"LOOP", "KO", "ALM"},
        held_us={"LOOP", "KO"},
        desde=D0,
        hasta=D1,
        earnings=[
            connector.normalize_earnings_row(
                {"symbol": "LOOP", "time": "time-pre-market", "epsForecast": "($0.05)"},
                date(2026, 10, 22),
            ),
            connector.normalize_earnings_row(
                {"symbol": "ALM", "time": "time-after-hours", "epsForecast": "$1.00"},
                date(2026, 10, 22),
            ),
            connector.normalize_earnings_row(
                {"symbol": "KO", "time": "time-not-supplied", "epsForecast": ""},
                date(2026, 10, 23),
            ),
        ],
        dividends=[
            connector.normalize_dividend_row(
                {"symbol": "KO", "dividend_Ex_Date": "10/16/2026",
                 "payment_Date": "10/30/2026", "dividend_Rate": 0.51},
                date(2026, 10, 16),
            ),
        ],
        actions=[{"ticker": "ALM", "action_type": "split", "effective_date": "2026-10-22",
                  "ratio": 2.0}],
    )
    got = [(e["date"], e["ticker"], e["type"], e["detail"]) for e in events]
    assert got == [
        ("2026-10-16", "KO", "dividend_ex", "0,5100 por accion"),
        ("2026-10-22", "LOOP", "earnings", "antes de la apertura, BPA estimado -0,05"),
        ("2026-10-22", "ALM", "corporate_action", "ratio 2"),
        ("2026-10-23", "KO", "earnings", None),
    ]
    assert all(e["source"] for e in events)
    assert not any(e["type"] == "dividend_pay" for e in events)
    assert not any("time-" in (e["detail"] or "") for e in events)


def test_no_invented_dates_when_source_has_none():
    events = svc.build_catalysts(
        held={"AAA"}, held_us={"AAA"}, desde=D0, hasta=D1,
        earnings=[{"symbol": "AAA", "date": None}], dividends=[], actions=[],
    )
    assert events == []


def test_combine_status():
    assert svc.combine_status("ok", "ok") == "ok"
    assert svc.combine_status("ok", "partial") == "partial"
    assert svc.combine_status("unavailable", "unavailable") == "unavailable"
    assert svc.combine_status("ok", "unavailable") == "partial"


def _route_client(engine, monkeypatch, *, earnings_rows, dividend_rows):
    import main
    from app.core.database import get_db

    async def fake_json(url, params, client):
        day = params["date"]
        if url == connector.EARNINGS_URL:
            return {"data": {"rows": earnings_rows if day == "2026-10-22" else []}}
        return {"data": {"calendar": {"rows": dividend_rows if day == "2026-10-16" else []}}}

    monkeypatch.setattr(connector, "_get_json", fake_json)

    def override():
        with Session(engine) as session:
            session.info["tenant_id"] = "tenant-test"
            yield session

    main.app.dependency_overrides[get_db] = override
    return TestClient(main.app, raise_server_exceptions=False), main


def test_catalysts_route_end_to_end_with_real_formats(engine, db, monkeypatch):
    _company(db, "LOOP", 10)
    _company(db, "ALM", 3, exchange="BME", currency="EUR")
    client, main = _route_client(
        engine,
        monkeypatch,
        earnings_rows=[
            {"symbol": "LOOP", "name": "Loop", "time": "time-pre-market", "epsForecast": "($0.05)"},
            {"symbol": "ALM", "name": "Otro emisor", "time": "time-after-hours"},
        ],
        dividend_rows=[
            {"symbol": "LOOP", "companyName": "Loop", "dividend_Ex_Date": "10/16/2026",
             "payment_Date": "10/30/2026", "dividend_Rate": 0.25},
        ],
    )
    try:
        res = client.get("/api/calendar/catalysts?desde=2026-10-14&hasta=2026-10-28")
    finally:
        main.app.dependency_overrides.clear()
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["held_count"] == 2
    assert [(e["date"], e["ticker"], e["type"]) for e in body["events"]] == [
        ("2026-10-16", "LOOP", "dividend_ex"),
        ("2026-10-22", "LOOP", "earnings"),
    ]
    assert body["events"][1]["detail"] == "antes de la apertura, BPA estimado -0,05"
