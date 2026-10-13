"""Los supuestos del modelo enlazan a la fuente real, resuelta desde la base."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, Company, Document, FinancialFact
from app.services.fact_source_links import attach_assumption_sources


def _db() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return Session(engine)


def _company(db: Session, ticker: str) -> Company:
    company = Company(ticker=ticker, name=ticker, exchange="TEST", currency="USD", sector="x", industry="x",
        company_type="standard", valuation_model="standard_dcf",
    )
    db.add(company)
    db.flush()
    return company


def _fact(db: Session, company: Company, source_id: int | None, metric: str = "revenue") -> FinancialFact:
    fact = FinancialFact(
        company_id=company.id, metric=metric, value=Decimal("100"), unit="USD", period="FY2025",
        fiscal_year=2025, source_id=source_id, source_type="sec", is_reported=True, confidence=Decimal("0.9"),
    )
    db.add(fact)
    db.flush()
    return fact


def test_assumptions_get_deduplicated_real_sources_and_ignore_unknown_ids():
    db = _db()
    company = _company(db, "AAA")
    doc = Document(
        company_id=company.id, title="10-K 2025", source_type="sec_filing",
        source_url="https://www.sec.gov/Archives/aaa-10k", published_at=datetime(2026, 2, 1, tzinfo=UTC),
    )
    db.add(doc)
    db.flush()
    f1, f2, f3 = _fact(db, company, doc.id), _fact(db, company, doc.id, "free_cash_flow"), _fact(db, company, None)
    payload = {
        "assumptions": {
            "revenue_growth": {"value": 0.1, "source_fact_ids": [f1.id, f2.id, 9999]},
            "fcf_margin": {"value": 0.2, "source_fact_ids": [f3.id]},
            "wacc": {"value": None, "source_fact_ids": []},
        }
    }
    out = attach_assumption_sources(db, company.id, payload)
    growth = out["assumptions"]["revenue_growth"]
    assert growth["fuentes"] == [
        {"fact_id": f1.id, "titulo": "10-K 2025", "url": "https://www.sec.gov/Archives/aaa-10k", "fecha": "2026-02-01"}
    ]
    # Un hecho sin documento y un id inexistente no inventan fuente.
    assert out["assumptions"]["fcf_margin"]["fuentes"] == []
    assert out["assumptions"]["wacc"]["fuentes"] == []
    # El resto del payload no se toca.
    assert growth["value"] == 0.1 and growth["source_fact_ids"] == [f1.id, f2.id, 9999]


def test_fact_of_another_company_is_not_resolved():
    db = _db()
    mine, other = _company(db, "MINE"), _company(db, "OTHR")
    doc = Document(company_id=other.id, title="Otra", source_type="sec_filing", source_url="https://x.example/y")
    db.add(doc)
    db.flush()
    foreign = _fact(db, other, doc.id)
    out = attach_assumption_sources(db, mine.id, {"assumptions": {"revenue_growth": {"source_fact_ids": [foreign.id]}}})
    assert out["assumptions"]["revenue_growth"]["fuentes"] == []


def test_payload_without_assumptions_is_returned_unchanged():
    db = _db()
    assert attach_assumption_sources(db, 1, {"status": "not_generated"}) == {"status": "not_generated"}
