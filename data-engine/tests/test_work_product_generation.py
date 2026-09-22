"""WorkProductService generation contracts.

Work products are what the user actually reads, so their honesty rules are
load-bearing: tenant context is mandatory, unsupported types are rejected,
missing thesis/price degrade to explicit "missing" states, risky claims are
surfaced only when their status warrants it, and data_as_of tracks the
newest real source date - never a fabricated one.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, Claim, Company, FinancialFact, MarketPrice
from app.services.work_product_service import WorkProductService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


@pytest.fixture
def company(db):
    c = Company(
        ticker="WPX", name="WPX", exchange="NYSE", currency="USD",
        sector="S", industry="I", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(c)
    db.commit()
    return c


def test_tenant_context_is_mandatory(db, company):
    db.info.pop("tenant_id", None)
    with pytest.raises(ValueError, match="Tenant"):
        WorkProductService().generate(db, product_type="one_page_memo", company=company)


def test_unsupported_type_rejected(db, company):
    with pytest.raises(ValueError, match="Unsupported"):
        WorkProductService().generate(db, product_type="horoscope", company=company)


def test_company_required_types_reject_missing_company(db):
    with pytest.raises(ValueError, match="requires a company"):
        WorkProductService().generate(db, product_type="full_thesis", company=None)


def test_portfolio_review_works_without_company(db):
    result = WorkProductService().generate(db, product_type="portfolio_review")
    assert result["ticker"] is None
    assert "portfolio_intelligence" in result["sections"]


def test_empty_company_yields_explicit_missing_states_and_warnings(db, company):
    result = WorkProductService().generate(db, product_type="one_page_memo", company=company)
    assert result["sections"]["investment_summary"] == {"status": "missing"}
    assert result["sections"]["market_price"] == {"status": "missing"}
    assert result["manifest"]["data_as_of"] is None
    assert "No canonical sources were available" in result["manifest"]["warnings"]
    assert "Data date is unavailable" in result["manifest"]["warnings"]


def test_data_as_of_tracks_newest_source_date(db, company):
    db.add(FinancialFact(
        company_id=company.id, metric="revenue", value=Decimal("100"),
        unit="USD", period="FY2025", fiscal_year=2025, source_type="filing",
    ))
    db.add(MarketPrice(
        company_id=company.id, date=date(2026, 9, 22),
        open=Decimal("10"), high=Decimal("11"), low=Decimal("9"),
        close=Decimal("10"), adj_close=Decimal("10"), source="Finnhub",
    ))
    db.commit()
    result = WorkProductService().generate(db, product_type="one_page_memo", company=company)
    assert result["manifest"]["data_as_of"] is not None
    assert result["sections"]["market_price"]["close"] == Decimal("10")
    assert "No canonical sources were available" not in result["manifest"]["warnings"]


def test_risks_surface_only_problematic_claim_statuses(db, company):
    for i, status in enumerate(["verified", "contradicted", "stale", "uncertain", "unverified"]):
        db.add(Claim(
            company_id=company.id, statement=f"claim {i}", status=status,
            confidence=Decimal("0.5"),
        ))
    db.commit()
    result = WorkProductService().generate(db, product_type="one_page_memo", company=company)
    kinds = {r["statement"] for r in result["sections"]["risks"] if r["kind"] == "claim"}
    assert kinds == {"claim 1", "claim 2", "claim 3", "claim 4"}


def test_valuation_memo_filters_to_its_metric_set(db, company):
    db.add(FinancialFact(
        company_id=company.id, metric="revenue", value=Decimal("100"),
        unit="USD", period="FY2025", fiscal_year=2025, source_type="filing",
    ))
    db.add(FinancialFact(
        company_id=company.id, metric="employee_count", value=Decimal("50"),
        unit="count", period="FY2025", fiscal_year=2025, source_type="filing",
    ))
    db.commit()
    result = WorkProductService().generate(db, product_type="valuation_memo", company=company)
    assert set(result["sections"]["metrics"]) == {"revenue"}
