"""F28: hechos de flujo con fp="FY" pero duracion trimestral (segmentos que la
SEC incluye en los 10-K) NO deben entrar como ejercicio anual. Caso real AAPL
FY2020: revenue 2020-03-28 (91 dias, Q2) quedo grabado como :FY (58,31 mil M)
y desplazo/corrompio el FY2020 real (274,515 mil M) y sus derivados.
Fix aprobado por Nico 25/9: anual = duracion 300-380 dias (como la via ESEF)."""

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


def _company(db, ticker="AAPL"):
    company = Company(
        ticker=ticker, name=ticker, exchange="NASDAQ", currency="USD",
        sector="S", industry="I", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


class _FakeSECAAPL:
    """AAPL-like: el 10-K de FY2020 trae fp=FY con duraciones mezcladas:
    el ejercicio completo (363 dias) y segmentos de Q2 (91 d) y Q4 (90 d)."""

    async def cik_for_ticker(self, ticker):
        return "0000320193"

    async def company_facts(self, cik):
        rev = "RevenueFromContractWithCustomerExcludingAssessedTax"
        return {"facts": {"us-gaap": {rev: {"units": {"USD": [
            {"fy": 2019, "fp": "FY", "form": "10-K", "start": "2018-09-30",
             "end": "2019-09-28", "val": 260_174_000_000, "filed": "2019-10-31"},
            {"fy": 2020, "fp": "FY", "form": "10-K", "start": "2019-09-29",
             "end": "2020-09-26", "val": 274_515_000_000, "filed": "2020-10-30"},
            {"fy": 2020, "fp": "FY", "form": "10-K", "start": "2019-12-29",
             "end": "2020-03-28", "val": 58_313_000_000, "filed": "2020-10-30"},
            {"fy": 2020, "fp": "FY", "form": "10-K", "start": "2020-06-28",
             "end": "2020-09-26", "val": 64_698_000_000, "filed": "2020-10-30"},
            {"fy": 2021, "fp": "FY", "form": "10-K", "start": "2020-09-27",
             "end": "2021-09-25", "val": 365_817_000_000, "filed": "2021-10-29"},
        ]}}}}}


def test_quarterly_segments_with_fp_fy_are_not_ingested_as_annual(db, monkeypatch):
    monkeypatch.setattr(ingestion, "SECClient", _FakeSECAAPL)
    company = _company(db)
    service = FinancialIngestionService()
    asyncio.run(service.refresh_from_sec(db=db, company=company))

    facts = list(db.scalars(
        select(FinancialFact).where(
            FinancialFact.company_id == company.id,
            FinancialFact.metric == "revenue",
            FinancialFact.is_reported.is_(True),
        )
    ))
    periods = {f.period: f.value for f in facts}
    assert periods.get("2019-09-28:FY") == Decimal("260174000000")
    assert periods.get("2020-09-26:FY") == Decimal("274515000000")
    assert periods.get("2021-09-25:FY") == Decimal("365817000000")
    # Los segmentos trimestrales etiquetados fp=FY quedan fuera:
    assert "2020-03-28:FY" not in periods
    # El ejercicio 2020 es el completo, no el segmento de Q4 (mismo `end`):
    by_year = {f.fiscal_year: f.value for f in facts}
    assert by_year[2020] == Decimal("274515000000")
