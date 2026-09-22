"""PeerAnalysisService contract tests.

Qualitative differences may only be emitted with linked evidence; the
quantitative side honestly reports insufficient_data when traceable
calculated metrics are missing.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, Claim, ClaimEvidence, Company
from app.services.peer_analysis_service import PeerAnalysisService
from app.services.peer_comparison_service import DEFAULT_PEER_METRICS


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
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


def _claim(db: Session, company_id: int, *, statement: str, claim_type: str,
           status: str = "verified", materiality: int = 5, with_evidence: bool = True) -> Claim:
    claim = Claim(
        company_id=company_id, statement=statement, claim_type=claim_type,
        status=status, materiality_score=materiality,
    )
    db.add(claim)
    db.flush()
    if with_evidence:
        db.add(ClaimEvidence(
            claim_id=claim.id, source_tier="tier_1_regulatory",
            evidence_type="supports", summary="ev",
        ))
        db.flush()
    return claim


def test_no_claims_no_metrics_is_honestly_empty(db):
    company = _company(db)
    result = PeerAnalysisService().analyze(db, company)
    assert result["status"] == "quantitative_only"
    assert result["advantages"] == []
    assert result["disadvantages"] == []
    # No calculated metrics persisted: every default metric is honestly insufficient.
    assert set(result["insufficient_data"]) == set(DEFAULT_PEER_METRICS)


def test_evidence_backed_claim_becomes_advantage(db):
    company = _company(db)
    claim = _claim(db, company.id, statement="Services mix expands gross margin",
                   claim_type="moat", materiality=8)
    result = PeerAnalysisService().analyze(db, company)
    assert result["status"] == "evidence_backed"
    assert len(result["advantages"]) == 1
    advantage = result["advantages"][0]
    assert advantage["basis"] == "evidence_backed_claim"
    assert advantage["dimension"] == "moat"
    assert advantage["claim_id"] == claim.id
    assert advantage["evidence"][0]["source_tier"] == "tier_1_regulatory"
    assert result["disadvantages"] == []


def test_risk_type_and_contradicted_status_become_disadvantages(db):
    company = _company(db)
    _claim(db, company.id, statement="Regulatory pressure on App Store",
           claim_type="risk", status="verified")
    _claim(db, company.id, statement="Switching costs protect the base",
           claim_type="moat", status="contradicted")
    _claim(db, company.id, statement="Ecosystem keeps expanding",
           claim_type="moat", status="verified", materiality=9)
    result = PeerAnalysisService().analyze(db, company)
    dimensions = {item["dimension"] for item in result["disadvantages"]}
    assert dimensions == {"risk", "moat"}
    assert len(result["disadvantages"]) == 2
    assert len(result["advantages"]) == 1
    assert result["advantages"][0]["statement"] == "Ecosystem keeps expanding"


def test_claim_without_evidence_is_never_emitted(db):
    company = _company(db)
    _claim(db, company.id, statement="Unsourced claim about dominance",
           claim_type="moat", with_evidence=False)
    result = PeerAnalysisService().analyze(db, company)
    assert result["status"] == "quantitative_only"
    assert result["advantages"] == []
    assert result["disadvantages"] == []
