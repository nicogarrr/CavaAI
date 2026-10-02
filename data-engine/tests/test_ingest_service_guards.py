"""FIX5: guardas de los defectos de ingesta SEC/FMP/ESEF.

Cada test protege un defecto concreto de la lista FIX5 (el eval de
`evals/ingest/` cubre los mismos via casos del dataset; aqui se fijan los
contratos del servicio: claves del resultado, colapso de claves, fail-closed de
entidad y fechas de publicacion).

Hermetico: sin red (el snapshot best-effort de filings/macro se sustituye).
"""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.entities import Base, Company, Document, FinancialFact
from app.services import financial_ingestion_service as ingestion
from app.services.financial_ingestion_service import (
    FinancialIngestionService,
    _norm_date,
    _period,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    with factory() as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


@pytest.fixture(autouse=True)
def _sin_free_data(monkeypatch):
    async def _stub(ticker, cik):
        return {"status": "skipped", "recent_filings": [], "macro": None}

    monkeypatch.setattr(ingestion, "_free_data_snapshot", _stub)


def _company(db, ticker="ACME", cik=None):
    company = Company(
        ticker=ticker, name=ticker, exchange="NASDAQ", currency="USD",
        sector="S", industry="I", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[],
        factor_tags=[], cik=cik,
    )
    db.add(company)
    db.commit()
    return company


def _facts(db, company, metric):
    return list(db.scalars(
        select(FinancialFact).where(
            FinancialFact.company_id == company.id, FinancialFact.metric == metric
        )
    ))


# --------------------------------------------------------------------------
# FIX5-2: _period normaliza epochs y conserva lo no parseable
# --------------------------------------------------------------------------


def test_period_normaliza_epoch_de_fmp():
    period, fiscal_year, fiscal_quarter = _period({"date": 1767139200, "period": "FY"})
    assert period == "2025-12-31:FY"
    assert fiscal_quarter == "FY"
    assert fiscal_year is None
    assert _norm_date(1767139200) == "2025-12-31"
    assert _norm_date("1767139200.0") == "2025-12-31"
    assert _norm_date(1767139200000) == "2025-12-31"  # epoch en milisegundos


def test_period_conserva_fechas_imposibles_verbatim():
    """Un cierre imposible debe llegar a la etiqueta para que la puerta
    no_lookahead lo acuse, no esfumarse en un `unknown` (FIX5-10)."""
    period, fiscal_year, _fiscal_quarter = _period(
        {"date": "2025-99-99", "period": "FY", "calendarYear": 2025}
    )
    assert period == "2025-99-99:FY"
    assert fiscal_year == 2025


