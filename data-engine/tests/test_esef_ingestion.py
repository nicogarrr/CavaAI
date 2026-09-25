"""ESEF ingestion: consolidated-only facts, annual windows, alias merge, honest gaps."""

import asyncio
import json
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


def _company(db, ticker="ITX"):
    company = Company(
        ticker=ticker, name=ticker, exchange="BME", currency="EUR",
        sector="S", industry="I", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


def _dur(val, start, end, dims=None):
    e = {"start": start, "end": end, "val": str(val), "decimals": 0, "lei": "L", "dims": dims or []}
    return e


def _inst(val, instant, dims=None):
    return {"instant": instant, "val": str(val), "decimals": 0, "lei": "L", "dims": dims or []}


SNAPSHOT = {
    "lei": "549300TTCXZOGZM2EY83",
    "ticker": "ITX",
    "entity_name": "INDUSTRIA DE DISEÑO TEXTIL, S.A.",
    "period_end": "2025-01-31",
    "fxo_id": "fxo-1",
    "fetched_at": "2026-09-24",
    "facts": {
        "ifrs-full:Revenue": {"iso4217:EUR": [
            _dur(38600000000, "2024-02-01", "2025-01-31"),
            _dur(35900000000, "2023-02-01", "2024-01-31"),
            _dur(9000000000, "2024-08-01", "2024-10-31"),  # trimestre: fuera
            _dur(500000000, "2024-02-01", "2025-01-31", dims=["ifrs-full:SegmentsAxis"]),  # miembro: fuera
        ]},
        "ifrs-full:ProfitLoss": {"iso4217:EUR": [_dur(5870000000, "2024-02-01", "2025-01-31")]},
        "ifrs-full:Assets": {"iso4217:EUR": [_inst(32000000000, "2025-01-31")]},
        "ifrs-full:CashAndCashEquivalents": {"iso4217:EUR": [_inst(7500000000, "2025-01-31")]},
        "ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities": {
            "iso4217:EUR": [_dur(1100000000, "2024-02-01", "2025-01-31")]
        },
        "ifrs-full:CashFlowsFromUsedInOperatingActivities": {
            "iso4217:EUR": [_dur(7200000000, "2024-02-01", "2025-01-31")]
        },
        "ifrs-full:GrossProfit": {"iso4217:EUR": [_dur(22300000000, "2024-02-01", "2025-01-31")]},
        "ifrs-full:ProfitLossFromOperatingActivities": {
            "iso4217:EUR": [_dur(6800000000, "2024-02-01", "2025-01-31")]
        },
        "ifrs-full:ProfitLossBeforeTax": {"iso4217:EUR": [_dur(7600000000, "2024-02-01", "2025-01-31")]},
        "ifrs-full:IncomeTaxExpenseContinuingOperations": {
            "iso4217:EUR": [_dur(1730000000, "2024-02-01", "2025-01-31")]
        },
        "ifrs-full:DepreciationAndAmortisationExpense": {
            "iso4217:EUR": [_dur(2700000000, "2024-02-01", "2025-01-31")]
        },
    },
}


def _run_refresh(db, monkeypatch, snapshot):
    monkeypatch.setattr(
        ingestion.esef_connector, "read_esef_snapshot", lambda ticker: snapshot
    )
    company = _company(db)
    service = FinancialIngestionService()
    return company, asyncio.run(service.refresh_from_esef(db=db, company=company))


def test_refresh_imports_only_consolidated_annual_facts(db, monkeypatch):
    company, result = _run_refresh(db, monkeypatch, SNAPSHOT)
    assert result["provider"] == "ESEF"
    assert result["lei"] == "549300TTCXZOGZM2EY83"
    facts = list(db.scalars(select(FinancialFact).where(FinancialFact.company_id == company.id)))
    by_metric_period = {(f.metric, f.period): f for f in facts}
    # annual revenue only (quarter + segment member excluded)
    assert ("revenue", "2025-01-31:FY") in by_metric_period
    assert ("revenue", "2024-01-31:FY") in by_metric_period
    assert by_metric_period[("revenue", "2025-01-31:FY")].value == Decimal("38600000000")
    assert len([f for f in facts if f.metric == "revenue"]) == 2
    # balance-sheet instants
    assert by_metric_period[("total_assets", "2025-01-31:FY")].value == Decimal("32000000000")
    # capex negated like SEC
    assert by_metric_period[("capital_expenditure", "2025-01-31:FY")].value == Decimal("-1100000000")
    assert all(f.source_type == "ESEF" for f in facts)
    assert all(f.unit == "EUR" for f in facts if f.is_reported)
    assert all(f.unit in ("EUR", "decimal") for f in facts)


def test_refresh_replaces_prior_esef_facts(db, monkeypatch):
    monkeypatch.setattr(ingestion.esef_connector, "read_esef_snapshot", lambda ticker: SNAPSHOT)
    company = _company(db)
    service = FinancialIngestionService()
    asyncio.run(service.refresh_from_esef(db=db, company=company))
    n1 = len(list(db.scalars(select(FinancialFact).where(FinancialFact.company_id == company.id))))
    asyncio.run(service.refresh_from_esef(db=db, company=company))  # second refresh
    n2 = len(list(db.scalars(select(FinancialFact).where(FinancialFact.company_id == company.id))))
    assert n1 == n2  # no duplicates


def test_missing_snapshot_raises_honestly(db, monkeypatch):
    monkeypatch.setattr(ingestion.esef_connector, "read_esef_snapshot", lambda ticker: None)
    company = _company(db)
    with pytest.raises(RuntimeError, match="Sin snapshot ESEF local"):
        asyncio.run(FinancialIngestionService().refresh_from_esef(db=db, company=company))


def test_alias_first_reporter_wins_never_summed(db, monkeypatch):
    snap = {
        **SNAPSHOT,
        "facts": {
            "ifrs-full:Revenue": {"iso4217:EUR": [_dur(100, "2024-01-01", "2024-12-31")]},
            "ifrs-full:RevenueFromInterest": {"iso4217:EUR": [_dur(50, "2024-01-01", "2024-12-31")]},
        },
    }
    company, _ = _run_refresh(db, monkeypatch, snap)
    facts = list(db.scalars(select(FinancialFact).where(FinancialFact.company_id == company.id)))
    assert len(facts) == 1
    assert facts[0].value == Decimal("100")  # Revenue informa primero; 50 NO se suma

def test_extended_map_and_derived_metrics(db, monkeypatch):
    company, _ = _run_refresh(db, monkeypatch, SNAPSHOT)
    facts = list(db.scalars(select(FinancialFact).where(FinancialFact.company_id == company.id)))
    by = {(f.metric, f.period): f for f in facts}
    fy = "2025-01-31:FY"
    # nuevos mapeados (reportados)
    assert by[("operating_income", fy)].value == Decimal("6800000000")
    assert by[("gross_profit", fy)].value == Decimal("22300000000")
    assert by[("income_before_tax", fy)].value == Decimal("7600000000")
    assert by[("income_tax_expense", fy)].value == Decimal("1730000000")
    assert by[("depreciation_amortization", fy)].value == Decimal("2700000000")
    # derivadas: nunca is_reported, confidence 0.85, EUR o decimal
    fcf = by[("free_cash_flow", fy)]
    assert fcf.value == Decimal("6100000000")  # 7.2B OCF - 1.1B capex
    assert fcf.is_reported is False
    ebitda = by[("ebitda", fy)]
    assert ebitda.value == Decimal("9500000000")  # 6.8B EBIT + 2.7B D&A
    assert ebitda.unit == "EUR"
    # la columna Numeric cuantiza ratios a 6 decimales: comparar con tolerancia
    assert abs(float(by[("gross_margin", fy)].value) - 22300000000 / 38600000000) < 1e-6
    assert abs(float(by[("operating_margin", fy)].value) - 6800000000 / 38600000000) < 1e-6
    assert abs(float(by[("net_margin", fy)].value) - 5870000000 / 38600000000) < 1e-6
    assert abs(float(by[("effective_tax_rate", fy)].value) - 1730000000 / 7600000000) < 1e-6
    assert abs(float(by[("fcf_margin", fy)].value) - 6100000000 / 38600000000) < 1e-6
    rg = by[("revenue_growth", fy)]
    assert abs(float(rg.value) - (38600000000 / 35900000000 - 1)) < 1e-6
    for m in ("free_cash_flow", "ebitda", "gross_margin", "operating_margin",
              "net_margin", "effective_tax_rate", "fcf_margin", "revenue_growth"):
        f = by[(m, fy)]
        assert f.is_reported is False
        assert f.source_type == "ESEF"
        assert f.confidence == Decimal("0.85")


def test_derived_metrics_skipped_when_inputs_missing(db, monkeypatch):
    snap = {
        **SNAPSHOT,
        "facts": {
            "ifrs-full:Revenue": {"iso4217:EUR": [_dur(100, "2024-02-01", "2025-01-31")]},
        },
    }
    company, _ = _run_refresh(db, monkeypatch, snap)
    facts = list(db.scalars(select(FinancialFact).where(FinancialFact.company_id == company.id)))
    metrics = {f.metric for f in facts}
    assert metrics == {"revenue"}  # sin OCF/EBIT no hay FCF, margenes ni EBITDA inventados



def _snapshot_with_debt(include_noncurrent=True):
    snap = json.loads(json.dumps(SNAPSHOT))
    snap["facts"]["ifrs-full:CurrentFinancialLiabilities"] = {"iso4217:EUR": [
        _inst(9000000000, "2025-01-31"), _inst(8500000000, "2024-01-31")]}
    if include_noncurrent:
        snap["facts"]["ifrs-full:NoncurrentFinancialLiabilities"] = {"iso4217:EUR": [
            _inst(21000000000, "2025-01-31"), _inst(23000000000, "2024-01-31")]}
    return snap


def test_total_debt_derived_from_components(db, monkeypatch):
    monkeypatch.setattr(
        ingestion.esef_connector, "read_esef_snapshot",
        lambda ticker: _snapshot_with_debt(),
    )
    service = FinancialIngestionService()
    company = _company(db)
    asyncio.run(service.refresh_from_esef(db=db, company=company))
    debts = db.scalars(
        select(FinancialFact).where(
            FinancialFact.company_id == company.id,
            FinancialFact.metric == "total_debt",
        )
    ).all()
    by_year = {f.fiscal_year: f for f in debts}
    assert set(by_year) == {2024, 2025}
    assert by_year[2025].value == Decimal(30000000000)
    assert by_year[2025].is_reported is False  # derivada, nunca reportada
    # componentes tambien importados como hechos propios
    assert db.scalar(
        select(FinancialFact).where(
            FinancialFact.company_id == company.id,
            FinancialFact.metric == "financial_liabilities_current",
        )
    )


def test_total_debt_honest_gap_with_one_component(db, monkeypatch):
    monkeypatch.setattr(
        ingestion.esef_connector, "read_esef_snapshot",
        lambda ticker: _snapshot_with_debt(include_noncurrent=False),
    )
    service = FinancialIngestionService()
    company = _company(db)
    asyncio.run(service.refresh_from_esef(db=db, company=company))
    assert not db.scalars(
        select(FinancialFact).where(
            FinancialFact.company_id == company.id,
            FinancialFact.metric == "total_debt",
        )
    ).all()
