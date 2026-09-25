"""Punto 3/6: ingesta de trimestres desde los 10-Q. Reglas:
- fp Q1-Q4 + form 10-Q; flujo = 70-110 dias (trimestre real). Los acumulados
  YTD (~180 dias), los TTM (~365 dias) y cualquier cosa en form 10-K quedan
  fuera. Los instantaneos de balance (sin start) pasan.
- fiscal_year=NULL deliberado: los consumidores anuales seleccionan por
  fiscal_year (u ordenan con nullslast), asi una fila :Q2 nunca compite con
  el ejercicio anual. period = "<end>:Q<n>", fiscal_quarter = Q1-Q4."""

import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.entities import Base, Company, FinancialFact
from app.services import financial_ingestion_service as ingestion
from app.services.financial_ingestion_service import FinancialIngestionService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    with factory() as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _company(db, ticker="ACME"):
    company = Company(
        ticker=ticker, name=ticker, exchange="NASDAQ", currency="USD",
        sector="S", industry="I", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


class _FakeSECQuarterly:
    """10-K con el FY2024 y 10-Q con: Q1 real (90d), Q2 real (91d) duplicado
    en dos filings (manda el filed mas reciente), YTD de Q2 (181d, fuera),
    TTM (365d, fuera), segmento mensual (31d, fuera) y balance instantaneo."""

    async def cik_for_ticker(self, ticker):
        return "0009999999"

    async def company_facts(self, cik):
        rev = "RevenueFromContractWithCustomerExcludingAssessedTax"
        eq = "StockholdersEquity"
        return {"facts": {"us-gaap": {
            rev: {"units": {"USD": [
                {"fy": 2025, "fp": "FY", "form": "10-K", "start": "2024-01-01",
                 "end": "2024-12-31", "val": 1000, "filed": "2025-02-10"},
                {"fy": 2025, "fp": "Q1", "form": "10-Q", "start": "2025-01-01",
                 "end": "2025-03-31", "val": 260, "filed": "2025-05-01"},
                {"fy": 2025, "fp": "Q2", "form": "10-Q", "start": "2025-04-01",
                 "end": "2025-06-30", "val": 270, "filed": "2025-08-01"},
                {"fy": 2025, "fp": "Q2", "form": "10-Q", "start": "2025-04-01",
                 "end": "2025-06-30", "val": 275, "filed": "2025-08-15"},
                {"fy": 2025, "fp": "Q2", "form": "10-Q", "start": "2025-01-01",
                 "end": "2025-06-30", "val": 530, "filed": "2025-08-01"},
                {"fy": 2025, "fp": "Q2", "form": "10-Q", "start": "2024-07-01",
                 "end": "2025-06-30", "val": 9999, "filed": "2025-08-01"},
                {"fy": 2025, "fp": "Q2", "form": "10-Q", "start": "2025-05-01",
                 "end": "2025-05-31", "val": 90, "filed": "2025-08-01"},
                {"fy": 2025, "fp": "Q2", "form": "10-K", "start": "2025-04-01",
                 "end": "2025-06-30", "val": 8888, "filed": "2026-02-10"},
            ]}},
            eq: {"units": {"USD": [
                {"fy": 2025, "fp": "Q2", "form": "10-Q",
                 "end": "2025-06-30", "val": 5000, "filed": "2025-08-01"},
            ]}},
        }}}


def _facts(db, company, metric):
    return list(db.scalars(
        select(FinancialFact).where(
            FinancialFact.company_id == company.id,
            FinancialFact.metric == metric,
            FinancialFact.is_reported.is_(True),
        )
    ))


def test_quarters_ingested_with_null_fiscal_year(db, monkeypatch):
    monkeypatch.setattr(ingestion, "SECClient", _FakeSECQuarterly)
    company = _company(db)
    service = FinancialIngestionService()
    asyncio.run(service.refresh_from_sec(db=db, company=company))

    revenue = _facts(db, company, "revenue")
    quarterly = {f.period: f for f in revenue if f.period.endswith((":Q1", ":Q2", ":Q3", ":Q4"))}
    assert set(quarterly) == {"2025-03-31:Q1", "2025-06-30:Q2"}
    # Manda el filed mas reciente (275, no 270):
    assert quarterly["2025-06-30:Q2"].value == Decimal("275")
    for fact in quarterly.values():
        assert fact.fiscal_year is None
        assert fact.fiscal_quarter in {"Q1", "Q2"}
    # El anual sigue igual:
    annual = [f for f in revenue if f.period.endswith(":FY")]
    assert len(annual) == 1 and annual[0].value == Decimal("1000")
    assert annual[0].fiscal_year == 2024
    # Balance instantaneo trimestral:
    equity = _facts(db, company, "total_equity")
    assert [f.period for f in equity] == ["2025-06-30:Q2"]
    assert equity[0].fiscal_year is None


def test_annual_consumers_do_not_see_quarters(db, monkeypatch):
    """_derive_sec_metrics indexa por fiscal_year: con NULL las filas :Qn
    no entran en derivados anuales (FCF, crecimiento, deuda neta)."""
    monkeypatch.setattr(ingestion, "SECClient", _FakeSECQuarterly)
    company = _company(db)
    service = FinancialIngestionService()
    asyncio.run(service.refresh_from_sec(db=db, company=company))

    derived = list(db.scalars(
        select(FinancialFact).where(
            FinancialFact.company_id == company.id,
            FinancialFact.is_reported.is_(False),
        )
    ))
    for fact in derived:
        assert fact.period.endswith(":FY")
