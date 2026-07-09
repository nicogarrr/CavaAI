from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Claim, Company, MoatAssessment
from app.services.source_hierarchy_service import SOURCE_TIERS


MOAT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "network_effects": ("network effect", "two-sided", "liquidity", "user network"),
    "switching_costs": ("switching cost", "lock-in", "migration", "retention"),
    "cost_advantage": ("cost advantage", "lowest cost", "unit cost", "procurement"),
    "scale": ("scale economy", "scale advantage", "fixed cost", "density"),
    "distribution": ("distribution", "dealer network", "channel", "installed base"),
    "brand": ("brand", "pricing power", "premium", "trust"),
    "regulation": ("license", "regulatory barrier", "spectrum", "approval"),
    "data": ("data advantage", "proprietary data", "dataset"),
    "ecosystem": ("ecosystem", "platform", "developer", "integration"),
    "capital_barrier": ("capital barrier", "capital intensive", "capex barrier"),
    "process_advantage": ("process advantage", "operational excellence", "know-how"),
}


class MoatService:
    def assess(self, db: Session, company: Company, *, persist: bool = True) -> dict:
        claims = list(
            db.scalars(
                select(Claim)
                .options(selectinload(Claim.evidence))
                .where(Claim.company_id == company.id)
            ).all()
        )
        results = []
        for moat_type, keywords in MOAT_KEYWORDS.items():
            relevant = [
                claim
                for claim in claims
                if (claim.metadata_ or {}).get("moat_type") == moat_type
                or any(keyword in claim.statement.lower() for keyword in keywords)
            ]
            supporting: list[int] = []
            contradicting: list[int] = []
            support_score = 0.0
            against_score = 0.0
            source_refs: list[dict] = []
            for claim in relevant:
                for evidence in claim.evidence:
                    tier = SOURCE_TIERS.get(
                        evidence.source_tier, SOURCE_TIERS["tier_unknown"]
                    )
                    weight = tier.trust_score * float(evidence.confidence)
                    if evidence.evidence_type == "supports":
                        support_score += weight
                        supporting.append(claim.id)
                    elif evidence.evidence_type in {
                        "contradicts",
                        "supersedes",
                    }:
                        against_score += weight
                        contradicting.append(claim.id)
                    source_refs.append(
                        {
                            "claim_id": claim.id,
                            "evidence_id": evidence.id,
                            "relation": evidence.evidence_type,
                            "source_tier": evidence.source_tier,
                            "weight": round(weight, 4),
                            "document_id": evidence.document_id,
                            "document_chunk_id": evidence.document_chunk_id,
                        }
                    )
            total = support_score + against_score
            evidence_count = len(source_refs)
            if total <= 0:
                strength = 0
                confidence = 0.0
                status = "insufficient_evidence"
                trend = "uncertain"
            else:
                balance = max(0.0, support_score - against_score)
                breadth_factor = min(1.0, evidence_count / 5)
                strength = round(100 * (balance / total) * breadth_factor)
                confidence = min(
                    0.95,
                    (total / max(1, evidence_count)) * breadth_factor,
                )
                status = (
                    "evidence_backed"
                    if evidence_count >= 2 and confidence >= 0.35
                    else "limited_evidence"
                )
                trend_markers = [
                    str((claim.metadata_ or {}).get("trend", ""))
                    for claim in relevant
                ]
                trend = next(
                    (
                        marker
                        for marker in trend_markers
                        if marker in {"strengthening", "stable", "eroding"}
                    ),
                    "stable" if status == "evidence_backed" else "uncertain",
                )
            persistence = (
                "high"
                if strength >= 70 and confidence >= 0.6
                else "medium"
                if strength >= 40 and confidence >= 0.4
                else "unproven"
            )
            payload = {
                "type": moat_type,
                "strength": strength,
                "trend": trend,
                "persistence": persistence,
                "confidence": round(confidence, 4),
                "status": status,
                "supporting_claim_ids": sorted(set(supporting)),
                "contradicting_claim_ids": sorted(set(contradicting)),
                "evidence_for": [
                    ref for ref in source_refs if ref["relation"] == "supports"
                ],
                "evidence_against": [
                    ref
                    for ref in source_refs
                    if ref["relation"] in {"contradicts", "supersedes"}
                ],
                "trace": {
                    "method": "MOAT_EVIDENCE_V1",
                    "support_score": round(support_score, 4),
                    "against_score": round(against_score, 4),
                    "keywords": list(keywords),
                },
            }
            results.append(payload)
            if persist:
                self._persist(db, company, payload)
        if persist:
            db.commit()
        evidence_backed = sum(
            1 for result in results if result["status"] == "evidence_backed"
        )
        return {
            "ticker": company.ticker,
            "status": (
                "evidence_backed"
                if evidence_backed
                else "insufficient_evidence"
            ),
            "methodology": (
                "Strength, trend and persistence are derived only from linked "
                "claim evidence weighted by the centralized source hierarchy."
            ),
            "moats": results,
        }

    def _persist(
        self, db: Session, company: Company, payload: dict
    ) -> MoatAssessment:
        assessment = db.scalar(
            select(MoatAssessment).where(
                MoatAssessment.company_id == company.id,
                MoatAssessment.moat_type == payload["type"],
            )
        )
        if assessment is None:
            assessment = MoatAssessment(
                company_id=company.id,
                moat_type=payload["type"],
            )
            db.add(assessment)
        assessment.strength = payload["strength"]
        assessment.trend = payload["trend"]
        assessment.persistence = payload["persistence"]
        assessment.confidence = Decimal(str(payload["confidence"]))
        assessment.status = payload["status"]
        assessment.supporting_claim_ids = payload["supporting_claim_ids"]
        assessment.contradicting_claim_ids = payload[
            "contradicting_claim_ids"
        ]
        assessment.assessment_trace = payload["trace"]
        return assessment
