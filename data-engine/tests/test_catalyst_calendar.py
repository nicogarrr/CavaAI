"""Calendario unico de catalizadores: formatos REALES de NASDAQ, cartera US y honestidad.

Las filas de NASDAQ usadas aqui replican lo medido en la API real: consenso
negativo entre parentesis ("($0.05)"), franjas "time-pre-market" /
"time-after-hours" / "time-not-supplied" y dividendos devueltos solo el dia de
su fecha ex.
"""

import asyncio
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


@pytest.fixture(autouse=True)
def _no_sec_network(monkeypatch):
    """Hermetico: los plazos 10-Q/10-K consultan EDGAR; por defecto sin red ni datos."""

    async def cik(*_args, **_kwargs):
        return "0000000001"

    async def empty_submissions(*_args, **_kwargs):
        return {}

    monkeypatch.setattr(svc, "_default_sec_fetchers", lambda: (cik, empty_submissions))


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


# Formato REAL de data.sec.gov/submissions (medido con AAPL, 2026-10): category,
# fiscalYearEnd "MMDD" y filings.recent con form/reportDate en listas paralelas.
APPLE = {
    "category": "Large accelerated filer",
    "fiscalYearEnd": "0926",
    "filings": {"recent": {
        "form": ["4", "10-Q", "8-K", "10-Q", "10-K"],
        "reportDate": ["2026-10-06", "2026-06-27", "2026-07-30", "2026-03-28", "2025-09-27"],
    }},
}


def _ev(data, ticker):
    event = svc.filing_deadline_event(data, ticker)
    assert event is not None
    return event


def test_filing_deadline_10k_after_third_quarter_large_accelerated():
    event = _ev(APPLE, "aapl")
    # 10-Q del 27-jun + 3 meses = cierre 27-sep (= mes de fin de ejercicio) -> 10-K, 60 dias.
    assert event["type"] == "filing_deadline" and event["ticker"] == "AAPL"
    assert event["date"] == "2026-11-26"
    assert event["title"] == "Plazo para presentar el 10-K (INFERIDO)"
    assert "60 dias" in event["detail"] and "Large accelerated filer" in event["detail"]
    assert event["source"] == svc.SOURCE_SEC_RULE


def test_filing_deadline_10q_and_category_variants():
    q1 = {**APPLE, "filings": {"recent": {"form": ["10-K"], "reportDate": ["2025-09-27"]}}}
    assert _ev(q1, "AAPL")["date"] == "2026-02-05"  # 27-dic + 40 d (jueves)
    accel = {**q1, "category": "Accelerated filer"}
    assert _ev(accel, "X")["date"] == "2026-02-05"
    small = {**q1, "category": "Non-accelerated filer"}
    assert _ev(small, "X")["date"] == "2026-02-10"  # 45 d


def test_filing_deadline_unknown_category_uses_max_and_says_so():
    data = {**APPLE, "category": ""}
    event = _ev(data, "AAPL")
    assert event["date"] == "2026-12-28"  # 27-sep + 90 d = sab 26-dic -> lunes 28
    assert "plazo maximo" in event["detail"]


def test_filing_deadline_no_data_means_none_not_invented():
    assert svc.filing_deadline_event({}, "X") is None
    assert svc.filing_deadline_event({**APPLE, "fiscalYearEnd": None}, "X") is None
    only_form4 = {**APPLE, "filings": {"recent": {"form": ["4"], "reportDate": ["2026-10-06"]}}}
    assert svc.filing_deadline_event(only_form4, "X") is None
    foreign = {**APPLE, "filings": {"recent": {"form": ["20-F"], "reportDate": ["2026-06-30"]}}}
    assert svc.filing_deadline_event(foreign, "X") is None


def test_add_months_end_of_month():
    assert svc._add_months(date(2026, 11, 30), 3) == date(2027, 2, 28)
    assert svc._add_months(date(2026, 12, 31), 3) == date(2027, 3, 31)
    assert svc._add_months(date(2026, 6, 27), 3) == date(2026, 9, 27)


def test_fetch_filing_deadlines_filters_range_and_reports_failures():
    async def cik(ticker):
        return None if ticker == "NOCIK" else "0000000001"

    async def subs(cik_):
        return APPLE

    out = asyncio.run(svc.fetch_filing_deadlines(
        {"AAPL", "NOCIK"}, date(2026, 11, 1), date(2026, 11, 30),
        cik_fetcher=cik, submissions_fetcher=subs,
    ))
    assert [e["ticker"] for e in out["events"]] == ["AAPL"]
    assert out["status"] == "partial"
    assert out["errors"] == ["Plazos 10-Q/10-K: EDGAR no disponible para NOCIK"]
    outside = asyncio.run(svc.fetch_filing_deadlines(
        {"AAPL"}, date(2026, 10, 14), date(2026, 10, 28), cik_fetcher=cik, submissions_fetcher=subs,
    ))
    assert outside == {"status": "ok", "events": [], "errors": []}


def test_fetch_filing_deadlines_exceptions_degrade_to_unavailable():
    async def boom(_):
        raise RuntimeError("secret-url-or-key")

    out = asyncio.run(svc.fetch_filing_deadlines(
        {"AAPL"}, D0, D1, cik_fetcher=boom, submissions_fetcher=boom,
    ))
    assert out["status"] == "unavailable" and out["events"] == []
    assert "secret" not in str(out)


def test_route_includes_filing_deadlines_sorted_and_status(engine, db, monkeypatch):
    _company(db, "AAPL", 5)

    async def cik(_ticker):
        return "0000320193"

    async def subs(_cik):
        return APPLE

    monkeypatch.setattr(svc, "_default_sec_fetchers", lambda: (cik, subs))
    client, main = _route_client(engine, monkeypatch, earnings_rows=[], dividend_rows=[])
    try:
        res = client.get("/api/calendar/catalysts?desde=2026-11-20&hasta=2026-11-30")
    finally:
        main.app.dependency_overrides.clear()
    body = res.json()
    assert res.status_code == 200 and body["status"] == "ok"
    assert [(e["date"], e["type"]) for e in body["events"]] == [("2026-11-26", "filing_deadline")]
