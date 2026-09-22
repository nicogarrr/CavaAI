"""ChatService deterministic-baseline contract tests.

The deterministic answer is the honesty floor of research chat: it cites
only stored, sourced rows, states plainly what is missing, and proposes
the next data step instead of inventing content.
"""

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import (
    Base,
    Claim,
    Company,
    FinancialFact,
    ThesisVersion,
)
from app.services.chat_service import ChatService, _decimal_to_float, _short


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _company(db: Session) -> Company:
    company = Company(
        ticker="AAPL", name="Apple", exchange="NASDAQ", currency="USD",
        sector="Tech", industry="Tech", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


def test_empty_company_is_blocked_with_honest_next_steps(db):
    company = _company(db)
    response = ChatService()._deterministic_answer(
        db, "What is the outlook for AAPL?", "company", "AAPL"
    )
    assert response.blocked is True
    assert response.model == "deterministic"
    assert f"No stored thesis exists yet for {company.ticker}." in response.answer
    assert "Calculation blocked: missing stored financial facts." in response.answer
    assert f"Create first thesis for {company.ticker}" in response.proposed_actions
    assert any("Ingest SEC/FMP" in action for action in response.proposed_actions)
    assert not response.sources


def test_populated_company_cites_stored_sourced_rows(db):
    company = _company(db)
    fact = FinancialFact(
        company_id=company.id, metric="revenue", value=Decimal("391000000000"),
        unit="USD", period="2025-09-27:FY", fiscal_year=2025,
        source_type="SEC", is_reported=True, confidence=Decimal("0.95"),
    )
    thesis = ThesisVersion(
        company_id=company.id, version=3, status="published",
        thesis_markdown="# t", executive_summary="e", rating="watch",
        current_price=Decimal("150"), expected_value=Decimal("200"),
    )
    db.add_all([fact, thesis])
    db.commit()

    response = ChatService()._deterministic_answer(
        db, "Revenue trend for AAPL?", "company", "AAPL"
    )
    assert response.blocked is False
    kinds = {source["type"] for source in response.sources}
    assert {"thesis_version", "financial_fact"} <= kinds
    fact_source = next(s for s in response.sources if s["type"] == "financial_fact")
    assert fact_source["source_type"] == "SEC"
    assert fact_source["value"] == 391000000000.0
    assert "AAPL thesis v3 is `published` with rating `watch`" in response.answer
    assert "Missing stored inputs" in response.answer  # other key metrics absent


def test_unverified_claim_surfaces_review_action(db):
    company = _company(db)
    thesis = ThesisVersion(
        company_id=company.id, version=1, status="draft",
        thesis_markdown="# t", executive_summary="e",
    )
    claim = Claim(
        company_id=company.id, statement="Margins will expand next year",
        status="unverified", confidence=Decimal("0.5"), materiality_score=6,
    )
    db.add_all([thesis, claim])
    db.commit()

    response = ChatService()._deterministic_answer(db, "AAPL claims?", "company", "AAPL")
    assert "Review unverified or contradicted claims" in response.proposed_actions
    assert "[unverified] Margins will expand next year" in response.answer


def test_ticker_resolved_from_question_text(db):
    _company(db)
    service = ChatService()
    resolved = service._resolve_company(db, "How is aapl positioned?", "company", None)
    assert resolved is not None and resolved.ticker == "AAPL"
    assert service._resolve_company(db, "general question", "portfolio", None) is None


def test_helpers_compact_and_convert():
    assert _short("  hello\n\n  world  ") == "hello world"
    assert len(_short("x" * 1000, limit=10)) <= 13  # truncated with ellipsis marker
    assert _decimal_to_float(Decimal("1.5")) == 1.5
    assert _decimal_to_float(None) is None
