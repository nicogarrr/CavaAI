from decimal import Decimal

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.models import Claim, Company
from app.services.peer_comparison_service import PeerComparisonService


LOWER_IS_BETTER = {"net_debt_to_ebitda"}


class PeerAnalysisService:
    def analyze(self, db: Session, company: Company, limit: int = 8) -> dict:
        comparison = PeerComparisonService().compare(
            db, company, limit=limit, refresh=False
        )
        advantages: list[dict] = []
        disadvantages: list[dict] = []
        insufficient: list[str] = []
        for metric, benchmark in comparison["benchmarks"].items():
            target_raw = benchmark.get("target_value")
            median_raw = benchmark.get("peer_median")
            if target_raw is None or median_raw is None:
                insufficient.append(metric)
                continue
            target = Decimal(target_raw)
            median = Decimal(median_raw)
            favorable = (
                target < median
                if metric in LOWER_IS_BETTER
                else target > median
            )
            item = {
                "dimension": metric,
                "target_value": str(target),
                "peer_median": str(median),
                "difference": str(target - median),
                "basis": "traceable_calculated_metric",
                "sample_size": benchmark["peer_sample_size"],
            }
            (advantages if favorable else disadvantages).append(item)

        qualitative_claims = list(
            db.scalars(
                select(Claim)
                .options(selectinload(Claim.evidence))
                .where(
                    Claim.company_id == company.id,
                    Claim.claim_type.in_(
                        [
                            "moat",
                            "peer",
                            "competitive_advantage",
                            "risk",
                            "thesis",
                        ]
                    ),
                )
                .order_by(desc(Claim.materiality_score), desc(Claim.confidence))
                .limit(30)
            ).all()
        )
        evidence_backed = []
        for claim in qualitative_claims:
            if not claim.evidence:
                continue
            evidence_backed.append(
                {
                    "claim_id": claim.id,
                    "statement": claim.statement,
                    "status": claim.status,
                    "claim_type": claim.claim_type,
                    "materiality_score": claim.materiality_score,
                    "evidence": [
                        {
                            "evidence_id": evidence.id,
                            "type": evidence.evidence_type,
                            "source_tier": evidence.source_tier,
                            "document_id": evidence.document_id,
                            "document_chunk_id": evidence.document_chunk_id,
                        }
                        for evidence in claim.evidence
                    ],
                }
            )

        for claim in evidence_backed:
            target_list = (
                disadvantages
                if claim["status"] in {"contradicted", "stale"}
                or claim["claim_type"] == "risk"
                else advantages
            )
            target_list.append(
                {
                    "dimension": claim["claim_type"],
                    "statement": claim["statement"],
                    "claim_id": claim["claim_id"],
                    "evidence": claim["evidence"],
                    "basis": "evidence_backed_claim",
                }
            )

        return {
            "ticker": company.ticker,
            "status": (
                "evidence_backed"
                if evidence_backed
                else "quantitative_only"
            ),
            "selection": {
                "basis": comparison["basis"],
                "trace": comparison.get("selection_trace", {}),
                "peers": [
                    row["ticker"]
                    for row in comparison["companies"]
                    if not row["is_target"]
                ],
            },
            "advantages": advantages,
            "disadvantages": disadvantages,
            "insufficient_data": insufficient,
            "methodology": (
                "Quantitative differences use traceable calculated metrics. "
                "Qualitative differences are emitted only when linked evidence exists."
            ),
        }
