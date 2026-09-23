"""SEC refresh conflict detection: batched FMP matching + honest conflicts.

The SEC/FMP reconciliation must flag material divergences (>5%) without one
query per SEC fact.
"""

import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

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


def _company(db: Session) -> Company:
    company = Company(
        ticker="AAA", name="AAA", exchange="NASDAQ", currency="USD",
        sector="S", industry="I", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


class _FakeSECClient:
    async def cik_for_ticker(self, ticker):
        return "0001234567"

    async def company_facts(self, cik):
        entries = [
            {"fy": year, "fp": "FY", "form": "10-K", "end": f"{year}-12-31", "val": value}
            for year, value in [(2024, 1000), (2023, 900)]
        ]
        return {
            "facts": {
                "us-gaap": {
                    "Revenues": {"units": {"USD": entries}},
                    "GrossProfit": {"units": {"USD": entries}},
                }
            }
        }


def _fmp_fact(db, company, metric, period, value):
    db.add(FinancialFact(
        company_id=company.id, metric=metric, value=Decimal(str(value)),
        unit="USD", period=period, fiscal_year=int(period[:4]), source_type="FMP",
    ))
    db.commit()


def test_conflicts_flagged_with_one_fmp_query(db, monkeypatch):
    monkeypatch.setattr(ingestion, "SECClient", _FakeSECClient)
    company = _company(db)
    # Matching period, >5% divergence on revenue; gross_profit matches.
    _fmp_fact(db, company, "revenue", "2024-12-31:FY", 1200)
    _fmp_fact(db, company, "gross_profit", "2024-12-31:FY", 1010)

    statements = []

    def listener(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", listener)
    try:
        result = asyncio.run(FinancialIngestionService().refresh_from_sec(db, company))
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", listener)

    assert result["status"] == "ingested"
    assert result["facts_imported"] == 4
    assert len(result["conflicts"]) == 1
    assert result["conflicts"][0].startswith("revenue:2024-12-31:FY FMP=1200 SEC=1000")
    # One SEC-facts read + one batched FMP lookup, not one query per SEC fact
    # (old code issued 1 + 4 for this fixture).
    fact_selects = [
        s for s in statements
        if s.lstrip().upper().startswith("SELECT") and "financial_facts" in s
    ]
    assert len(fact_selects) == 2
