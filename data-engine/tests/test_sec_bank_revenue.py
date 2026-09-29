"""Revenue compuesto para bancos: intereses netos + ingresos no financieros.

Los bancos (WFC, MS, BPOP) no reportan un tag de revenue agregado en XBRL;
sus ingresos son InterestIncomeExpenseNet + NoninterestIncome. La composicion
solo rellena periodos sin tag agregado (un alias real siempre gana) y exige
AMBOS componentes (fail closed: nunca un subtotal parcial). Decision
aprobada dentro del lote "hazlo ya todo" (29/9): modelarlo como la suma.
"""

import asyncio
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.entities import Base, Company, Document, FinancialFact
from app.services import financial_ingestion_service as ingestion
from app.services.financial_ingestion_service import (
    BANK_REVENUE_CONCEPT,
    FinancialIngestionService,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    with factory() as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _company(db, ticker="WFC"):
    company = Company(
        ticker=ticker, name=ticker, exchange="NYSE", currency="USD",
        sector="Financials", industry="Banks", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


def _fy(fy_, val):
    return {"fy": fy_, "fp": "FY", "form": "10-K", "start": f"{fy_}-01-01",
            "end": f"{fy_}-12-31", "val": val, "filed": f"{fy_ + 1}-03-01"}


def _q1(year, val):
    return {"fy": year, "fp": "Q1", "form": "10-Q", "start": f"{year}-01-01",
            "end": f"{year}-03-31", "val": val, "filed": f"{year}-05-01"}


class _FakeBankSEC:
    """Banco: Revenues solo hasta 2022; desde 2023 los dos componentes."""

    async def cik_for_ticker(self, ticker):
        return "0000072971"

    async def company_facts(self, cik):
        return {"facts": {"us-gaap": {
            "Revenues": {"units": {"USD": [_fy(2022, 100)]}},
            "InterestIncomeExpenseNet": {"units": {"USD": [
                _fy(2023, 60), _fy(2024, 70), _q1(2025, 20),
            ]}},
            "NoninterestIncome": {"units": {"USD": [
                _fy(2023, 40), _fy(2024, 30), _q1(2025, 5),
            ]}},
        }}}


class _FakeHalfBankSEC:
    """Solo intereses netos: sin NoninterestIncome no se compone nada."""

    async def cik_for_ticker(self, ticker):
        return "0000000001"

    async def company_facts(self, cik):
        return {"facts": {"us-gaap": {
            "InterestIncomeExpenseNet": {"units": {"USD": [_fy(2024, 70)]}},
        }}}


def _with_anchors(payload, close_month):
    anchors = {}
    for concept in payload["facts"]["us-gaap"].values():
        for entries in concept["units"].values():
            for e in entries:
                if not str(e.get("form", "")).startswith("10-K"):
                    continue
                accn = f"K{e.get('fy')}-{e.get('filed')}"
                e["accn"] = accn
                start, end = e.get("start"), str(e.get("end") or "")
                if len(end) < 10:
                    continue
                if not start:
                    if end[5:7] == close_month:
                        anchors[accn] = end
                    continue
                span = (date.fromisoformat(end) - date.fromisoformat(str(start))).days
                if 300 <= span <= 380 and end[5:7] == close_month:
                    anchors[accn] = end
    return payload, anchors


def _anchor_fake(cls, close_month="12"):
    original = cls.company_facts

    async def company_facts(self, cik):
        payload = getattr(self, "_cached_payload", None)
        if payload is None:
            payload = await original(self, cik)
            self._cached_payload = payload
        return payload

    async def annual_report_anchors(self, cik):
        anchors = getattr(self, "_cached_anchors", None)
        if anchors is None:
            _, anchors = _with_anchors(await self.company_facts(cik), close_month)
            self._cached_anchors = anchors
        return anchors

    cls.company_facts = company_facts
    cls.annual_report_anchors = annual_report_anchors
    return cls


_anchor_fake(_FakeBankSEC)
_anchor_fake(_FakeHalfBankSEC)


def _revenue_facts(db, company_id):
    return list(db.scalars(
        select(FinancialFact).where(
            FinancialFact.company_id == company_id,
            FinancialFact.metric == "revenue",
        )
    ))


def test_bank_revenue_composed_from_components(db, monkeypatch):
    monkeypatch.setattr(ingestion, "SECClient", _FakeBankSEC)
    company = _company(db)
    asyncio.run(FinancialIngestionService().refresh_from_sec(db=db, company=company))

    annual = {f.fiscal_year: f for f in _revenue_facts(db, company.id) if f.fiscal_quarter == "FY"}
    assert annual[2022].value == Decimal("100")  # alias real gana en 2022
    assert annual[2023].value == Decimal("100")  # 60 + 40 compuestos
    assert annual[2024].value == Decimal("100")  # 70 + 30 compuestos

    quarterly = [f for f in _revenue_facts(db, company.id) if f.fiscal_quarter == "Q1"]
    assert len(quarterly) == 1
    assert quarterly[0].value == Decimal("25")  # 20 + 5 compuestos
    assert quarterly[0].period == "2025-03-31:Q1"

    # Proveniencia: los periodos compuestos quedan marcados con el concepto
    # sintetico; el de 2022 conserva el tag real.
    document = db.scalar(select(Document).where(
        Document.company_id == company.id, Document.source_type == "SEC"))
    usage = (document.metadata_ or {}).get("xbrl_concept_by_metric_period", {})
    assert usage["revenue"]["2022-12-31"] == "Revenues"
    assert usage["revenue"]["2023-12-31"] == BANK_REVENUE_CONCEPT
    assert usage["revenue"]["2024-12-31"] == BANK_REVENUE_CONCEPT


def test_bank_revenue_fail_closed_without_both_components(db, monkeypatch):
    monkeypatch.setattr(ingestion, "SECClient", _FakeHalfBankSEC)
    company = _company(db, ticker="HALF")
    asyncio.run(FinancialIngestionService().refresh_from_sec(db=db, company=company))
    assert _revenue_facts(db, company.id) == []
