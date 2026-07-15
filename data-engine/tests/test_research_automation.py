from decimal import Decimal
from uuid import uuid4

from sqlalchemy import delete, select

from app.core.database import SessionLocal, init_db
from app.models import (
    Claim,
    ClaimEvidence,
    Company,
    Document,
    DocumentChunk,
    EvidenceSuggestion,
    ResearchAlert,
    ResearchReview,
    ThesisChange,
    ThesisEdge,
    ThesisNode,
    ThesisVersion,
)
from app.services.claim_intelligence_service import ClaimIntelligenceService
from app.services.thesis_graph_service import ThesisGraphService


def test_document_scan_detects_numeric_contradiction_and_creates_review():
    init_db()
    ticker = f"T{uuid4().hex[:8].upper()}"
    db = SessionLocal()
    company = Company(
        ticker=ticker,
        name="Automation Test",
        exchange="TEST",
        currency="USD",
        sector="Technology",
        industry="Software",
        company_type="operating_company",
        valuation_model="standard_dcf",
        factor_tags=["software"],
    )
    db.add(company)
    db.flush()
    claim = Claim(
        company_id=company.id,
        statement="Revenue guidance for 2026 is 100 million dollars.",
        claim_type="guidance",
        status="supported",
        confidence=Decimal("0.80"),
        materiality_score=9,
    )
    document = Document(
        company_id=company.id,
        title="Quarterly filing",
        source_type="10-q",
    )
    db.add_all([claim, document])
    db.flush()
    db.add(
        DocumentChunk(
            document_id=document.id,
            chunk_index=0,
            text=(
                "The company reported that revenue guidance for 2026 is "
                "80 million dollars after customer delays."
            ),
            token_count=15,
        )
    )
    db.commit()

    result = ClaimIntelligenceService().scan_document(
        db, document, auto_apply=True
    )
    db.refresh(claim)
    assert result["applied"] == 1
    assert claim.status == "contradicted"
    assert db.scalar(
        select(ResearchReview).where(ResearchReview.claim_id == claim.id)
    )
    assert db.scalar(
        select(ResearchAlert).where(
            ResearchAlert.company_id == company.id
        )
    )
    thesis_change = db.scalar(
        select(ThesisChange).where(
            ThesisChange.company_id == company.id
        )
    )
    assert thesis_change is not None
    assert thesis_change.change_type == "claim_contradiction"
    assert thesis_change.affected_claim_ids == [claim.id]

    claim_id = claim.id
    company_id = company.id
    document_id = document.id
    db.execute(
        delete(ClaimEvidence).where(ClaimEvidence.claim_id == claim_id)
    )
    db.execute(
        delete(EvidenceSuggestion).where(
            EvidenceSuggestion.company_id == company_id
        )
    )
    db.execute(
        delete(ResearchAlert).where(
            ResearchAlert.company_id == company_id
        )
    )
    db.execute(
        delete(ResearchReview).where(
            ResearchReview.company_id == company_id
        )
    )
    db.execute(
        delete(ThesisChange).where(
            ThesisChange.company_id == company_id
        )
    )
    db.execute(
        delete(DocumentChunk).where(
            DocumentChunk.document_id == document_id
        )
    )
    db.delete(claim)
    db.delete(document)
    db.delete(company)
    db.commit()
    db.close()


def test_thesis_graph_maps_claims_to_structural_dependencies():
    init_db()
    ticker = f"G{uuid4().hex[:8].upper()}"
    db = SessionLocal()
    company = Company(
        ticker=ticker,
        name="Graph Test",
        exchange="TEST",
        currency="USD",
        sector="Industrials",
        industry="Aerospace",
        company_type="pre_revenue",
        valuation_model="pre_revenue",
        factor_tags=["space", "speculative"],
    )
    db.add(company)
    db.flush()
    thesis = ThesisVersion(
        company_id=company.id,
        version=1,
        status="draft",
        thesis_markdown="# Test",
        executive_summary="Launch cadence and funding determine commercialization.",
    )
    db.add(thesis)
    db.flush()
    claim = Claim(
        company_id=company.id,
        thesis_version_id=thesis.id,
        statement="Constellation funding must avoid excessive dilution.",
        claim_type="funding",
        materiality_score=9,
        metadata_={
            "invalidation_conditions": [
                "Funding gap exceeds available liquidity."
            ]
        },
    )
    db.add(claim)
    db.commit()

    _, nodes, edges = ThesisGraphService().build(db, company, thesis)
    funding = next(
        node for node in nodes if node.node_key == "dependency:funding"
    )
    assert claim.id in funding.claim_ids
    assert funding.invalidation_conditions
    assert edges

    node_ids = [node.id for node in nodes]
    db.execute(
        delete(ThesisEdge).where(
            ThesisEdge.from_node_id.in_(node_ids)
        )
    )
    db.execute(
        delete(ThesisNode).where(
            ThesisNode.company_id == company.id
        )
    )
    db.delete(claim)
    db.delete(thesis)
    db.delete(company)
    db.commit()
    db.close()
