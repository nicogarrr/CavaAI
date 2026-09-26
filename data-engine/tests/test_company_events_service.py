"""CompanyEventsService contract tests (ficha Quartr-like, Fase 1).

Reglas: nada inventado (ausencia = estado honesto), fuente+fecha en cada
pieza, red siempre inyectada (tests herméticos), degradación a
``unavailable`` cuando una fuente falla.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, Company, Document
from app.services.company_events_service import CompanyEventsService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _company(db: Session, *, cik: str | None = "0000320193") -> Company:
    company = Company(
        ticker="AAPL", name="Apple Inc.", exchange="NASDAQ", currency="USD",
        sector="Tech", industry="Tech", cik=cik, company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[],
        factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


def _calendar_payload(rows: list[dict]) -> dict:
    return {"earningsCalendar": rows}


def _future_row(symbol: str = "AAPL", days: int = 30) -> dict:
    day = (datetime.now(UTC).date() + timedelta(days=days)).isoformat()
    return {
        "symbol": symbol, "date": day, "hour": "amc", "quarter": 4, "year": 2026,
        "epsEstimate": 2.0, "epsActual": None,
        "revenueEstimate": 130000000000, "revenueActual": None,
    }


def _past_row(symbol: str = "AAPL", days: int = 60) -> dict:
    day = (datetime.now(UTC).date() - timedelta(days=days)).isoformat()
    return {
        "symbol": symbol, "date": day, "hour": "amc", "quarter": 3, "year": 2026,
        "epsEstimate": 1.9, "epsActual": 1.91,
        "revenueEstimate": 90000000000, "revenueActual": 91000000000,
    }


def _eps_history() -> list[dict]:
    period = (datetime.now(UTC).date() - timedelta(days=60)).isoformat()
    return [{
        "symbol": "AAPL", "estimate": 1.9, "actual": 1.91, "period": period,
        "surprise": 0.01, "surprisePercent": 0.52, "year": 2026, "quarter": 3,
    }]


def _submissions() -> dict:
    return {
        "filings": {
            "recent": {
                "accessionNumber": ["0000320193-26-000123", "0000320193-26-000099"],
                "form": ["10-Q", "4"],
                "filingDate": ["2026-08-01", "2026-08-02"],
                "reportDate": ["2026-06-27", ""],
                "primaryDocument": ["aapl-20260627.htm", "form4.htm"],
            }
        }
    }


import asyncio
from urllib.parse import urlparse


def _run(coro):
    return asyncio.run(coro)


# -- Eventos -----------------------------------------------------------------

def test_events_next_and_history_with_sources(db):
    company = _company(db)
    service = CompanyEventsService(
        db,
        calendar_fetcher=lambda f, t: asyncio.sleep(0, _calendar_payload([_future_row(), _past_row()])),
        eps_history_fetcher=lambda s: asyncio.sleep(0, _eps_history()),
    )
    out = _run(service.get_events(company))
    assert out["calendar_status"] == "ok"
    assert out["eps_history_status"] == "ok"
    assert out["next_event"]["eps_estimate"] == 2.0
    assert out["next_event"]["source"].startswith("Finnhub")
    assert len(out["history"]) == 1
    row = out["history"][0]
    assert row["eps_actual"] == 1.91
    assert row["revenue_actual"] == 91000000000
    assert row["eps_surprise_percent"] == 0.52
    assert out["note"] is None


def test_events_filters_other_symbols(db):
    company = _company(db)
    service = CompanyEventsService(
        db,
        calendar_fetcher=lambda f, t: asyncio.sleep(0, _calendar_payload([_future_row("MSFT")])),
        eps_history_fetcher=lambda s: asyncio.sleep(0, []),
    )
    out = _run(service.get_events(company))
    assert out["next_event"] is None
    assert out["history"] == []
    assert out["calendar_status"] == "ok"


def test_events_all_sources_down_is_honest(db):
    company = _company(db)

    async def _none(*args):
        return None

    service = CompanyEventsService(
        db, calendar_fetcher=_none, eps_history_fetcher=_none,
    )
    out = _run(service.get_events(company))
    assert out["calendar_status"] == "unavailable"
    assert out["eps_history_status"] == "unavailable"
    assert out["next_event"] is None
    assert out["history"] == []
    assert out["note"]  # estado honesto, no ceros inventados


# -- Filings ------------------------------------------------------------------

def test_filings_maps_forms_and_links(db):
    company = _company(db)
    service = CompanyEventsService(
        db, submissions_fetcher=lambda c: asyncio.sleep(0, _submissions()),
    )
    out = _run(service.get_filings(company))
    assert out["sec_status"] == "ok"
    assert len(out["filings"]) == 1  # Form 4 queda fuera del set permitido
    filing = out["filings"][0]
    assert filing["form"] == "10-Q"
    assert filing["filed_at"] == "2026-08-01"
    assert filing["period"] == "2026-06-27"
    assert filing["url"].endswith("aapl-20260627.htm")
    assert urlparse(filing["url"]).hostname == "www.sec.gov"
    assert filing["source"] == "SEC EDGAR"


def test_filings_no_cik_honest_state(db):
    company = _company(db, cik=None)

    async def _no_cik(ticker):
        return None

    service = CompanyEventsService(db, cik_fetcher=_no_cik)
    out = _run(service.get_filings(company))
    assert out["filings"] == []
    assert out["sec_status"] == "unavailable"
    assert "Sin filings SEC" in (out["note"] or "")


def test_filings_sec_down_but_db_docs_listed(db):
    company = _company(db)
    db.add(Document(
        company_id=company.id, title="ESEF XBRL facts - AAPL",
        source_type="ESEF", source_url=None, storage_uri=None,
        published_at=None, checksum="x", metadata_={}, tenant_id="tenant-test",
    ))
    db.commit()

    async def _none(*args):
        return None

    service = CompanyEventsService(
        db, submissions_fetcher=_none,
    )
    out = _run(service.get_filings(company))
    assert out["filings"] == []
    assert out["sec_status"] == "unavailable"
    assert out["documents"] and out["documents"][0]["source_type"] == "ESEF"
