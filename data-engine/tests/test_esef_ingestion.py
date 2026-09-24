"""ESEF ingestion: consolidated-only facts, annual windows, alias merge, honest gaps."""

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
    assert all(f.unit == "EUR" for f in facts)


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
    with pytest.raises(RuntimeError, match="ESEF snapshot not found"):
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
