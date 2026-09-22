"""ThesisEvidenceService contract tests.

Thesis evidence is the raw material of professional theses: SEC annual
facts must prefer 10-K over 10-Q, market data must land dated and
sourced, and refresh passes must never duplicate rows or cross tenant
boundaries.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.models.entities import (
    Base,
    Company,
    Document,
    FinancialFact,
    MarketPrice,
)
from app.services.thesis_evidence_service import ThesisEvidenceService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _company(db: Session, *, name: str = "") -> Company:
    company = Company(
        ticker="AAPL", name=name, exchange="", currency="USD",
        sector="Tech", industry="Tech", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


def _gaap(entries_by_tag: dict[str, list[dict]]) -> dict:
    return {tag: {"units": {"USD": entries}} for tag, entries in entries_by_tag.items()}


# -- SEC annual extraction ----------------------------------------------------

def test_extract_latest_annual_prefers_10k_over_newer_10q():
    us_gaap = _gaap(
        {
            "Revenues": [
                {"form": "10-K", "val": 100, "end": "2025-09-27", "filed": "2025-11-01"},
                {"form": "10-Q", "val": 30, "end": "2026-06-27", "filed": "2026-08-01"},
            ]
        }
    )
    out = ThesisEvidenceService()._extract_latest_annual(us_gaap)
    assert out["revenue"]["value"] == 100
    assert out["revenue"]["period"] == "2025-09-27:FY"
    assert out["revenue"]["fiscal_year"] == 2025
    assert out["revenue"]["fiscal_quarter"] == "FY"
    assert out["revenue"]["concept"] == "Revenues"


def test_extract_latest_annual_falls_back_to_latest_quarter():
    us_gaap = _gaap(
        {
            "Assets": [
                {"form": "10-Q", "val": 10, "end": "2026-03-28", "filed": "2026-05-01"},
                {"form": "10-Q", "val": 12, "end": "2026-06-27", "filed": "2026-08-01"},
            ]
        }
    )
    out = ThesisEvidenceService()._extract_latest_annual(us_gaap)
    assert out["total_assets"]["value"] == 12
    assert out["total_assets"]["period"] == "2026-06-27:10-Q"
    assert out["total_assets"]["fiscal_quarter"] is None


def test_extract_latest_annual_first_tag_wins_never_sums():
    us_gaap = _gaap(
        {
            "Revenues": [{"form": "10-K", "val": 100, "end": "2025-09-27", "filed": "2025-11-01"}],
            "SalesRevenueNet": [{"form": "10-K", "val": 90, "end": "2025-09-27", "filed": "2025-11-01"}],
        }
    )
    out = ThesisEvidenceService()._extract_latest_annual(us_gaap)
    assert out["revenue"]["value"] == 100
    assert out["revenue"]["concept"] == "Revenues"


def test_extract_latest_annual_skips_entries_without_value_or_end():
    us_gaap = _gaap(
        {
            "NetIncomeLoss": [
                {"form": "10-K", "val": None, "end": "2025-09-27", "filed": "2025-11-01"},
                {"form": "10-K", "val": 42, "filed": "2025-11-01"},
            ]
        }
    )
    assert ThesisEvidenceService()._extract_latest_annual(us_gaap) == {}


# -- Finnhub market ingest -----------------------------------------------------

def _stub_market(service, quote=None, profile=None, quote_exc=None):
    if quote_exc is not None:
        service._fetch_quote = lambda ticker: (_ for _ in ()).throw(quote_exc)
    else:
        service._fetch_quote = lambda ticker: quote
    service._fetch_profile = lambda ticker: profile


def test_ingest_market_persists_dated_sourced_price_and_market_cap(db):
    company = _company(db, name="AAPL")
    service = ThesisEvidenceService()
    _stub_market(
        service,
        quote={"c": 190.5},
        profile={"name": "Apple Inc.", "marketCapitalization": 2900.0, "exchange": "NASDAQ"},
    )
    result = service._ingest_market(db, company)
    db.commit()

    assert result["status"] == "ok"
    assert result["price"] == 190.5
    today = datetime.now(UTC).date()
    price_row = db.scalar(
        select(MarketPrice).where(
            MarketPrice.company_id == company.id, MarketPrice.date == today
        )
    )
    assert price_row is not None
    assert price_row.close == Decimal("190.5")
    assert price_row.source == "Finnhub"

    cap = db.scalar(
        select(FinancialFact).where(
            FinancialFact.company_id == company.id,
            FinancialFact.metric == "market_cap",
        )
    )
    assert cap is not None
    # Finnhub reports millions of USD; the fact stores full USD.
    assert cap.value == Decimal("2900000000")
    assert cap.source_type == "Finnhub"
    assert cap.confidence == Decimal("0.75")

    # Placeholder name (== ticker) and empty exchange get filled from profile.
    assert company.name == "Apple Inc."
    assert company.exchange == "NASDAQ"


def test_ingest_market_without_quote_keeps_honest_pending_state(db):
    company = _company(db)
    service = ThesisEvidenceService()
    _stub_market(service, quote_exc=RuntimeError("no key"), profile=None)
    result = service._ingest_market(db, company)
    db.commit()

    assert result["status"] == "pending"
    assert "detail" in result
    assert db.scalar(
        select(func.count())
        .select_from(MarketPrice)
        .where(MarketPrice.company_id == company.id)
    ) == 0


def test_ingest_market_is_idempotent_within_a_day(db):
    company = _company(db)
    service = ThesisEvidenceService()
    _stub_market(
        service,
        quote={"c": 190.5},
        profile={"name": "Apple Inc.", "marketCapitalization": 2900.0, "exchange": "NASDAQ"},
    )
    service._ingest_market(db, company)
    _stub_market(service, quote={"c": 191.0}, profile={"marketCapitalization": 2900.0})
    service._ingest_market(db, company)
    db.commit()

    rows = db.scalars(
        select(MarketPrice).where(MarketPrice.company_id == company.id)
    ).all()
    assert len(rows) == 1
    assert rows[0].close == Decimal("191.0")
    assert db.scalar(
        select(func.count())
        .select_from(FinancialFact)
        .where(
            FinancialFact.company_id == company.id,
            FinancialFact.metric == "market_cap",
        )
    ) == 1


# -- document dedupe + tenant-scoped fact replacement --------------------------

def test_get_or_create_document_is_idempotent(db):
    company = _company(db)
    service = ThesisEvidenceService()
    first = service._get_or_create_document(
        db, company, title="10-K 2025", source_type="SEC", source_url="https://sec.gov/x"
    )
    second = service._get_or_create_document(
        db, company, title="10-K 2025", source_type="SEC", source_url="https://sec.gov/x"
    )
    db.commit()
    assert first.id == second.id
    assert second.metadata_["auto_ingested"] is True
    assert db.scalar(
        select(func.count()).select_from(Document).where(Document.company_id == company.id)
    ) == 1


def test_replace_facts_scoped_to_source_type_and_tenant(db):
    company = _company(db)
    today = datetime.now(UTC).date().isoformat()

    def _fact(metric, source_type, tenant_id):
        return FinancialFact(
            company_id=company.id, metric=metric, value=Decimal("1"), unit="USD",
            period=today, source_type=source_type, is_reported=True,
            confidence=Decimal("0.5"), tenant_id=tenant_id,
        )

    db.add(_fact("revenue", "SEC", "tenant-test"))
    db.add(_fact("assets", "Finnhub", "tenant-test"))
    db.flush()

    # Cross-tenant rows cannot be written from a tenant-scoped session
    # (the before_flush hook forbids it), so seed the other tenant's fact
    # through a separate tenant-less session, as a different tenant's own
    # connection would.
    engine = db.get_bind()
    with Session(engine) as other_db:
        other_db.add(_fact("revenue", "SEC", "other-tenant"))
        other_db.commit()

    ThesisEvidenceService()._replace_facts(db, company, "SEC")
    db.commit()

    remaining = db.scalars(
        select(FinancialFact).where(FinancialFact.company_id == company.id)
    ).all()
    assert {(f.metric, f.source_type) for f in remaining} == {("assets", "Finnhub")}

    with Session(engine) as verify_db:
        survivor = verify_db.scalar(
            select(FinancialFact).where(
                FinancialFact.company_id == company.id,
                FinancialFact.source_type == "SEC",
            )
        )
    assert survivor is not None
    assert survivor.tenant_id == "other-tenant"
