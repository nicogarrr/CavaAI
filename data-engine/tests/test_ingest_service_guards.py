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
# FIX5-1: refresh_from_sec recibe as_of y filtra por fecha de publicacion
# --------------------------------------------------------------------------


class _FakeSECConCortes:
    async def cik_for_ticker(self, ticker):
        return "0000000001"

    async def company_facts(self, cik):
        return {"cik": 1, "facts": {"us-gaap": {
            "Revenues": {"units": {"USD": [
                {"fy": 2999, "fp": "FY", "form": "10-K", "start": "2999-01-01",
                 "end": "2999-12-31", "val": 42000000000, "filed": "3000-02-10",
                 "accn": "0000000001-99-000001"},
                {"fy": 2025, "fp": "FY", "form": "10-K", "start": "2025-01-01",
                 "end": "2025-12-31", "val": 5000000000, "filed": "2026-02-10",
                 "accn": "0000000001-25-000001"},
            ]}}}}}

    async def annual_report_anchors(self, cik):
        return {"0000000001-99-000001": "2999-12-31", "0000000001-25-000001": "2025-12-31"}


def test_as_of_excluye_lo_no_publicado_y_se_declara(db, monkeypatch):
    monkeypatch.setattr(ingestion, "SECClient", _FakeSECConCortes)
    company = _company(db)
    result = asyncio.run(
        FinancialIngestionService().refresh_from_sec(db=db, company=company, as_of=date(2026, 10, 1))
    )
    assert result["status"] == "ingested"
    assert result["as_of"] == "2026-10-01"
    assert result["date_filter_applied"] is True
    periods = {f.period for f in _facts(db, company, "revenue")}
    assert periods == {"2025-12-31:FY"}  # el FY2999 (filed 3000) no entra


def test_sin_as_of_el_filtro_de_fecha_no_se_aplica(db, monkeypatch):
    monkeypatch.setattr(ingestion, "SECClient", _FakeSECConCortes)
    company = _company(db)
    result = asyncio.run(
        FinancialIngestionService().refresh_from_sec(db=db, company=company)
    )
    assert result["date_filter_applied"] is False
    assert result["as_of"] is None
    periods = {f.period for f in _facts(db, company, "revenue")}
    assert periods == {"2999-12-31:FY", "2025-12-31:FY"}


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


# --------------------------------------------------------------------------
# FIX5-3: refresh_from_fmp contrasta el symbol de cada fila
# --------------------------------------------------------------------------


class _FakeFMPConSymbol:
    async def income_statement(self, ticker, limit=5):
        return [
            {"symbol": "OTRA", "date": "2025-12-31", "period": "FY", "calendarYear": 2025,
             "revenue": 999000000000, "netIncome": 99000000000},
            {"symbol": "ACME", "date": "2025-12-31", "period": "FY", "calendarYear": 2025,
             "revenue": 5000000000, "netIncome": 500000000},
        ]

    async def balance_sheet(self, ticker, limit=5):
        return []

    async def cash_flow(self, ticker, limit=5):
        return []

    async def ratios(self, ticker, limit=5):
        return []

    async def company_profile(self, ticker):
        return []

    async def quote(self, ticker):
        return []


def test_refresh_from_fmp_rechaza_filas_de_otro_simbolo(db):
    company = _company(db, "ACME")
    result = asyncio.run(
        FinancialIngestionService().refresh_from_fmp(db, company, client=_FakeFMPConSymbol())
    )
    assert result["rows_rechazadas_por_symbol"] == 1
    revenues = _facts(db, company, "revenue")
    assert [f.value for f in revenues] == [Decimal("5000000000")]
    assert all(f.period == "2025-12-31:FY" for f in revenues)


# --------------------------------------------------------------------------
# FIX5-8: shares_diluted no mezcla saldo instantaneo con promedio ponderado
# --------------------------------------------------------------------------


class _FakeSECShares:
    async def cik_for_ticker(self, ticker):
        return "0000000001"

    async def company_facts(self, cik):
        return {"cik": 1, "facts": {"us-gaap": {
            "WeightedAverageNumberOfDilutedSharesOutstanding": {"units": {"shares": [
                {"fy": 2025, "fp": "FY", "form": "10-K", "start": "2025-01-01",
                 "end": "2025-12-31", "val": 1176000000, "filed": "2026-02-10",
                 "accn": "0000000001-25-000001"},
            ]}},
            "CommonStockSharesOutstanding": {"units": {"shares": [
                {"fy": 2025, "fp": "FY", "form": "10-K", "end": "2025-12-31",
                 "val": 1250000000, "filed": "2026-03-01", "accn": "0000000001-25-000001"},
            ]}},
        }}}

    async def annual_report_anchors(self, cik):
        return {"0000000001-25-000001": "2025-12-31"}


class _FakeSECSharesTrimestral(_FakeSECShares):
    async def company_facts(self, cik):
        return {"cik": 1, "facts": {"us-gaap": {
            "WeightedAverageNumberOfDilutedSharesOutstanding": {"units": {"shares": [
                {"fy": 2025, "fp": "Q2", "form": "10-Q", "start": "2025-04-01",
                 "end": "2025-06-30", "val": 1170000000, "filed": "2025-08-01",
                 "accn": "0000000001-25-000010"},
            ]}},
            "CommonStockSharesOutstanding": {"units": {"shares": [
                {"fy": 2025, "fp": "Q3", "form": "10-Q", "end": "2025-08-15",
                 "val": 1260000000, "filed": "2025-08-15", "accn": "0000000001-25-000010"},
            ]}},
        }}}


def test_shares_diluted_es_el_promedio_y_el_saldo_es_otra_metrica(db, monkeypatch):
    monkeypatch.setattr(ingestion, "SECClient", _FakeSECShares)
    company = _company(db)
    asyncio.run(FinancialIngestionService().refresh_from_sec(db=db, company=company))
    diluted = _facts(db, company, "shares_diluted")
    assert [f.value for f in diluted] == [Decimal("1176000000")]
    outstanding = _facts(db, company, "shares_outstanding")
    assert [f.value for f in outstanding] == [Decimal("1250000000")]


def test_el_conteo_de_portada_no_entra_como_shares_diluted_trimestral(db, monkeypatch):
    monkeypatch.setattr(ingestion, "SECClient", _FakeSECSharesTrimestral)
    company = _company(db)
    asyncio.run(FinancialIngestionService().refresh_from_sec(db=db, company=company))
    diluted = _facts(db, company, "shares_diluted")
    assert [f.period for f in diluted] == ["2025-06-30:Q2"]
    outstanding = _facts(db, company, "shares_outstanding")
    assert [f.period for f in outstanding] == ["2025-08-15:Q3"]


