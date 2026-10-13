from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.entities import Base, Company, Document, FinancialFact, Tenant
from app.services.filing_intelligence import KEY
from app.services.filing_yoy_service import comparison


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        tenant = Tenant(external_id="yoy-one", name="One")
        other = Tenant(external_id="yoy-two", name="Two")
        company = Company(ticker="YOY", name="Yoy", exchange="NASDAQ", currency="USD",
                          company_type="holding", valuation_model="unassigned")
        session.add_all([tenant, other, company])
        session.flush()
        session.info.update(tenant_id=tenant.id, company_id=company.id, other_tenant=other.id)
        yield session
    engine.dispose()


def doc(db, period, form="10-K", n=1, tenant=None, meta=None, url=None):
    row = Document(tenant_id=tenant or db.info["tenant_id"], company_id=db.info["company_id"], title=form,
                   source_type="SEC", source_url=url or f"https://www.sec.gov/Archives/edgar/data/1/{n}/r.htm",
                   checksum=f"h{n}", published_at=datetime(2026, 1, 1, tzinfo=UTC),
                   metadata_={"form": form, "report_date": period, **(meta or {})})
    active = db.info["tenant_id"]
    db.info["tenant_id"] = row.tenant_id
    db.add(row)
    db.flush()
    db.info["tenant_id"] = active
    return row


def fact(db, metric, value, period, source=None, **kw):
    db.add(FinancialFact(tenant_id=db.info["tenant_id"], company_id=db.info["company_id"], metric=metric,
                         value=Decimal(value), period=period, source_id=source.id if source else None,
                         source_type="SEC", **kw))
    db.flush()


def test_no_documents_is_insufficient(db):
    assert comparison(db, db.info["company_id"], "10-K", 1)["status"] == "insufficient_data"


def test_pairs_annual_figures_with_source_and_derived_change(db):
    now, before = doc(db, "2026-09-30", n=2), doc(db, "2025-09-30", n=1)
    fact(db, "revenue", "1500", "2026-09-30:FY", now)
    fact(db, "revenue", "1000", "2025-09-30:FY", before)
    fact(db, "net_income", "-5", "2026-09-30:FY", now)
    fact(db, "net_income", "10", "2025-09-30:FY", before)
    fact(db, "gross_profit", "7", "2026-09-30:FY", now)
    result = comparison(db, db.info["company_id"], "10-K", 1)
    assert result["status"] == "ready"
    by = {f["metric"]: f for f in result["figures"]}
    assert by["revenue"]["change_pct"] == "50.0" and by["revenue"]["highlight"]
    assert by["revenue"]["current"]["source"]["url"].startswith("https://www.sec.gov/")
    assert by["net_income"]["change_pct"] is None  # cambio de signo: sin %
    assert by["gross_profit"]["label"] == "SIN_DATOS" and by["gross_profit"]["previous"] is None


def test_quarterly_never_mixes_fy_and_other_quarters(db):
    doc(db, "2026-06-30", "10-Q", 2, meta={"fiscal_quarter": "Q2"})
    doc(db, "2025-06-30", "10-Q", 1, meta={"fiscal_quarter": "Q2"})
    fact(db, "revenue", "10", "2026-06-30:Q2")
    fact(db, "revenue", "8", "2025-06-30:Q2")
    fact(db, "revenue", "999", "2025-06-30:FY")
    rev = comparison(db, db.info["company_id"], "10-Q", 1)["figures"]
    assert len(rev) == 1 and rev[0]["previous"]["value"].startswith("8")


def test_no_comparable_prior_and_non_official_and_other_tenant_excluded(db):
    doc(db, "2026-09-30", n=2)
    doc(db, "2025-09-30", n=1, tenant=db.info["other_tenant"])
    doc(db, "2025-09-30", n=3, url="https://example.com/fake.htm")
    result = comparison(db, db.info["company_id"], "10-K", 1)
    assert result["status"] == "insufficient_data" and result["total"] == 1


def test_text_diff_only_when_persisted_for_same_prior(db):
    now, before = doc(db, "2026-09-30", n=2), doc(db, "2025-09-30", n=1)
    assert "text_reason" in comparison(db, db.info["company_id"], "10-K", 1)
    now.metadata_ = {**now.metadata_, KEY: {"diff": {"status": "changed"}, "previous_source": {"document_id": before.id}}}
    db.flush()
    assert comparison(db, db.info["company_id"], "10-K", 1)["text"] == {"status": "changed"}
    now.metadata_ = {**now.metadata_, KEY: {"diff": {"status": "changed"}, "previous_source": {"document_id": 999}}}
    db.flush()
    assert comparison(db, db.info["company_id"], "10-K", 1)["text"] is None


def test_page_past_end_and_invalid_form(db):
    doc(db, "2026-09-30")
    assert comparison(db, db.info["company_id"], "10-K", 5)["status"] == "insufficient_data"
    with pytest.raises(ValueError):
        comparison(db, db.info["company_id"], "8-K", 1)
