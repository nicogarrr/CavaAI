"""ClaimIntelligenceService contract tests.

Claim intelligence decides when new evidence supports, contradicts,
supersedes or stales a thesis claim - the classification must be
deterministic, conservative (uncertain when evidence is thin) and never
invent relations the text does not support.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, Claim, Company
from app.services.claim_intelligence_service import ClaimIntelligenceService


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


def _claim(db: Session, company: Company, statement: str, **kwargs) -> Claim:
    claim = Claim(
        company_id=company.id,
        statement=statement,
        confidence=Decimal("0.6"),
        materiality_score=7,
        **kwargs,
    )
    db.add(claim)
    db.commit()
    return claim


# -- statement extraction ------------------------------------------------------

def test_extract_statements_keeps_material_numbered_and_forward_looking():
    text = (
        "Revenue grew 12 percent year over year driven by services momentum. "
        "The sky was blue and the office plants were watered on Tuesday. "
        "Management expects margin expansion toward 30 percent next year."
    )
    statements = ClaimIntelligenceService().extract_statements(text)
    extracted = [s.text for s in statements]
    assert any("Revenue grew 12" in s for s in extracted)
    assert any("expects margin expansion" in s for s in extracted)
    # No material term, number or forward-looking marker: dropped.
    assert not any("office plants" in s for s in extracted)


def test_extract_statements_dedupes_and_caps_length_and_limit():
    repeated = "Guidance targets revenue growth above 20 percent for next year. "
    text = repeated * 20
    statements = ClaimIntelligenceService().extract_statements(text, limit=5)
    assert 1 <= len(statements) <= 5  # deduped to one unique sentence
    short = ClaimIntelligenceService().extract_statements("Too short. " * 30)
    assert short == []
    scores = [s.materiality_score for s in statements]
    assert scores == sorted(scores, reverse=True)


# -- claim matching --------------------------------------------------------------

def test_match_claims_ranks_by_similarity_and_respects_floor(db):
    company = _company(db)
    close = _claim(db, company, "Services revenue will grow double digits next year")
    unrelated = _claim(db, company, "The board appointed a new audit chair in March")
    matches = ClaimIntelligenceService().match_claims(
        db,
        company_id=company.id,
        statement="Services revenue will grow double digits next year",
    )
    assert matches
    assert matches[0].claim.id == close.id
    assert matches[0].similarity == pytest.approx(1.0, abs=1e-9)
    assert all(m.claim.id != unrelated.id for m in matches)


# -- relation classification -----------------------------------------------------

def test_classify_relation_marks_expired_claim_stale(db):
    company = _company(db)
    claim = _claim(
        db, company, "Revenue will grow 10 percent this year",
        metadata_={"valid_until": (datetime.now(UTC) - timedelta(days=1)).isoformat()},
    )
    result = ClaimIntelligenceService().classify_relation(
        claim=claim, candidate="anything", similarity=0.9, use_jev=False
    )
    assert result.relation == "stale"
    assert result.confidence == 0.95


def test_classify_relation_detects_supersession_marker(db):
    company = _company(db)
    claim = _claim(db, company, "Guidance revenue growth 10 percent next fiscal year")
    result = ClaimIntelligenceService().classify_relation(
        claim=claim,
        candidate="Updated guidance revenue growth 14 percent next fiscal year",
        similarity=0.85,
        use_jev=False,
    )
    assert result.relation == "superseded"


def test_classify_relation_detects_numeric_contradiction(db):
    company = _company(db)
    claim = _claim(db, company, "Operating margin reached 25 percent this quarter")
    result = ClaimIntelligenceService().classify_relation(
        claim=claim,
        candidate="Operating margin reached 10 percent this quarter",
        similarity=0.85,
        use_jev=False,
    )
    assert result.relation == "contradicted"
    assert "numeric" in result.rationale.lower()


def test_classify_relation_supported_on_close_match(db):
    company = _company(db)
    claim = _claim(db, company, "Services revenue will grow double digits next year")
    result = ClaimIntelligenceService().classify_relation(
        claim=claim,
        candidate="Services revenue will grow double digits next year",
        similarity=0.95,
        use_jev=False,
    )
    assert result.relation == "supported"


def test_classify_relation_uncertain_when_evidence_thin(db):
    company = _company(db)
    claim = _claim(db, company, "Services revenue will grow double digits next year")
    result = ClaimIntelligenceService().classify_relation(
        claim=claim,
        candidate="Wearables demand softened in several regions this quarter",
        similarity=0.25,
        use_jev=False,
    )
    assert result.relation == "uncertain"
    assert 0.45 <= result.confidence <= 0.74
