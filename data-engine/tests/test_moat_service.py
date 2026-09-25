"""MoatService contract tests (MOAT_EVIDENCE_V1).

The moat assessment feeds the professional thesis and the red team: it
must derive strength/trend/persistence ONLY from linked claim evidence
weighted by the centralized source hierarchy, persist honestly
(insufficient_evidence, never invented moats), and read() must return
persisted rows only - never derive on GET.
"""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.entities import Base, Claim, ClaimEvidence, Company, MoatAssessment
from app.services.moat_service import MOAT_KEYWORDS, MoatService


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


def _claim(db: Session, company_id: int, statement: str, metadata: dict | None = None) -> Claim:
    claim = Claim(company_id=company_id, statement=statement, metadata_=metadata or {})
    db.add(claim)
    db.flush()
    return claim


def _evidence(db: Session, claim_id: int, *, tier: str, kind: str = "supports", confidence: float = 0.9):
    db.add(ClaimEvidence(
        claim_id=claim_id, source_tier=tier, evidence_type=kind,
        confidence=confidence, summary="ev",
    ))
    db.flush()


def test_no_claims_every_moat_insufficient_evidence(db):
    company = _company(db)
    result = MoatService().assess(db, company)
    assert result["status"] == "insufficient_evidence"
    assert len(result["moats"]) == len(MOAT_KEYWORDS)
    for moat in result["moats"]:
        assert moat["strength"] == 0
        assert moat["status"] == "insufficient_evidence"
        assert moat["trend"] == "uncertain"
        assert moat["persistence"] == "unproven"
        assert moat["confidence"] == 0.0
        assert moat["trace"]["method"] == "MOAT_EVIDENCE_V1"


def test_supporting_primary_evidence_builds_strength(db):
    company = _company(db)
    claim = _claim(db, company.id, "Brand pricing power sustains margins")
    _evidence(db, claim.id, tier="tier_1_regulatory", confidence=0.9)
    _evidence(db, claim.id, tier="tier_1_regulatory", confidence=0.9)

    result = MoatService().assess(db, company)
    brand = next(m for m in result["moats"] if m["type"] == "brand")
    # weight = 1.0 * 0.9 per evidence; support = 1.8, total = 1.8,
    # breadth = 2/5 = 0.4 -> strength = 100 * 1 * 0.4 = 40.
    assert brand["strength"] == 40
    # confidence = (1.8/2) * 0.4 = 0.36 -> evidence_backed (>= 2 refs, >= 0.35).
    assert brand["confidence"] == pytest.approx(0.36)
    assert brand["status"] == "evidence_backed"
    assert brand["trend"] == "stable"  # default when evidence_backed, no marker
    # strength 40 meets the medium bar but confidence 0.36 < 0.4 -> honest unproven.
    assert brand["persistence"] == "unproven"
    assert brand["supporting_claim_ids"] == [claim.id]
    assert brand["contradicting_claim_ids"] == []
    assert brand["trace"]["support_score"] == pytest.approx(1.8)
    assert result["status"] == "evidence_backed"
    # Unrelated moat types stay honestly empty.
    scale = next(m for m in result["moats"] if m["type"] == "scale")
    assert scale["status"] == "insufficient_evidence"


def test_contradicting_evidence_cancels_strength(db):
    company = _company(db)
    claim = _claim(db, company.id, "High switching cost locks in customers")
    _evidence(db, claim.id, tier="tier_2_company", confidence=0.8)
    _evidence(db, claim.id, tier="tier_2_company", kind="contradicts", confidence=0.8)

    result = MoatService().assess(db, company)
    moat = next(m for m in result["moats"] if m["type"] == "switching_costs")
    # support = against = 0.9 * 0.8 = 0.72 -> balance 0 -> strength 0.
    assert moat["strength"] == 0
    assert moat["supporting_claim_ids"] == [claim.id]
    assert moat["contradicting_claim_ids"] == [claim.id]
    assert len(moat["evidence_against"]) == 1
    assert moat["status"] == "limited_evidence"  # confidence 0.288 < 0.35
    assert moat["trend"] == "uncertain"


def test_metadata_moat_type_matches_without_keyword_and_trend_marker_wins(db):
    company = _company(db)
    claim = _claim(
        db, company.id, "Fixed cost density improved again",
        metadata={"moat_type": "scale", "trend": "eroding"},
    )
    _evidence(db, claim.id, tier="tier_unknown", confidence=0.9)
    _evidence(db, claim.id, tier="tier_unknown", confidence=0.9)

    result = MoatService().assess(db, company)
    scale = next(m for m in result["moats"] if m["type"] == "scale")
    assert scale["supporting_claim_ids"] == [claim.id]
    assert scale["trend"] == "eroding"  # metadata marker wins
    # Note: "scale advantage" is not in the statement, only metadata matched.
    keyword_only = next(m for m in result["moats"] if m["type"] == "regulation")
    assert keyword_only["status"] == "insufficient_evidence"


def test_assess_persists_and_read_returns_only_persisted(db):
    company = _company(db)
    claim = _claim(db, company.id, "Ecosystem lock-in across devices")
    _evidence(db, claim.id, tier="tier_1_regulatory", confidence=0.9)
    _evidence(db, claim.id, tier="tier_1_regulatory", confidence=0.9)

    # read() never derives: with claims but no assessments it stays empty.
    before = MoatService().read(db, company)
    assert before["moats"] == []
    assert before["status"] == "insufficient_evidence"

    MoatService().assess(db, company)
    rows = db.scalars(select(MoatAssessment).where(MoatAssessment.company_id == company.id)).all()
    # F29: solo se persiste el tipo con evidencia; los tipos sin evidencia
    # no se guardan como ceros (una no-evaluacion no es una puntuacion).
    assert sorted(row.moat_type for row in rows) == ["ecosystem", "switching_costs"]

    after = MoatService().read(db, company)
    assert after["status"] == "evidence_backed"
    eco = next(m for m in after["moats"] if m["type"] == "ecosystem")
    assert eco["strength"] == 40
    assert eco["supporting_claim_ids"] == [claim.id]
    assert after["methodology"] == "Persisted source-weighted moat assessments."


def test_reassessment_updates_in_place_no_duplicates(db):
    company = _company(db)
    claim = _claim(db, company.id, "Brand trust drives premium pricing")
    _evidence(db, claim.id, tier="tier_1_regulatory", confidence=0.9)
    _evidence(db, claim.id, tier="tier_1_regulatory", confidence=0.9)

    MoatService().assess(db, company)
    MoatService().assess(db, company)
    rows = db.scalars(
        select(MoatAssessment).where(
            MoatAssessment.company_id == company.id,
            MoatAssessment.moat_type == "brand",
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].strength == 40


def test_zero_evidence_run_persists_nothing(db):
    """F29: sin evidencia no hay filas - el GET dira "sin evaluacion"."""
    company = _company(db)
    # Claim financiero sin keywords de foso y sin evidencia: como en prod.
    _claim(db, company.id, "AAPL revenue is 416161000000.000000 for 2025-09-27:FY.")
    result = MoatService().assess(db, company)
    assert result["status"] == "insufficient_evidence"
    rows = db.scalars(select(MoatAssessment).where(MoatAssessment.company_id == company.id)).all()
    assert rows == []


def test_zero_evidence_run_never_overwrites_real_assessment(db):
    """F29: una corrida posterior sin evidencia conserva la evaluacion real."""
    company = _company(db)
    claim = _claim(db, company.id, "Brand pricing power sustains margins")
    _evidence(db, claim.id, tier="tier_1_regulatory", confidence=0.9)
    _evidence(db, claim.id, tier="tier_1_regulatory", confidence=0.9)
    MoatService().assess(db, company)
    before = db.scalar(
        select(MoatAssessment).where(
            MoatAssessment.company_id == company.id,
            MoatAssessment.moat_type == "brand",
        )
    )
    assert before.strength == 40

    # Segunda corrida: la evidencia desaparece (p.ej. claims regenerados).
    for ev in list(claim.evidence):
        db.delete(ev)
    db.flush()
    MoatService().assess(db, company)
    after = db.scalar(
        select(MoatAssessment).where(
            MoatAssessment.company_id == company.id,
            MoatAssessment.moat_type == "brand",
        )
    )
    assert after.strength == 40
    assert after.status == "evidence_backed"
