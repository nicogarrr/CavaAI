from __future__ import annotations

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models import (
    CalculatedMetric,
    Claim,
    Company,
    Document,
    FinancialFact,
    FundamentalModelVersion,
    ResearchAlert,
    ResearchReview,
    ThesisChange,
    ThesisVersion,
    ValuationModel,
)
from app.schemas import CompanySnapshotOut


class CompanySnapshotService:
    """Build the small workspace bootstrap exclusively from persisted rows.

    This service deliberately contains no calculator, model builder, graph
    builder, document chunk loader or commit. Refreshes belong to explicit POST
    endpoints so a GET can be cached, retried and observed without side effects.
    """

    def build(self, db: Session, company: Company) -> CompanySnapshotOut:
        thesis = db.scalar(
            select(ThesisVersion)
            .where(ThesisVersion.company_id == company.id)
            .order_by(desc(ThesisVersion.version))
            .limit(1)
        )
        model = db.scalar(
            select(FundamentalModelVersion)
            .where(FundamentalModelVersion.company_id == company.id)
            .order_by(desc(FundamentalModelVersion.version))
            .limit(1)
        )
        valuation_model = db.scalar(
            select(ValuationModel)
            .where(ValuationModel.company_id == company.id)
            .order_by(desc(ValuationModel.version), desc(ValuationModel.created_at))
            .limit(1)
        )
        recent_changes = list(
            db.scalars(
                select(ThesisChange)
                .where(ThesisChange.company_id == company.id)
                .order_by(desc(ThesisChange.created_at))
                .limit(10)
            ).all()
        )
        counts = self._counts(db, company.id)
        missing: list[str] = []
        if counts["documents"] == 0:
            missing.append("documents")
        if counts["facts"] == 0:
            missing.append("financial_facts")
        if thesis is None:
            missing.append("thesis")
        if model is None:
            missing.append("long_term_model")

        review_required = counts["open_reviews"] > 0 or counts["open_alerts"] > 0
        completed = 4 - len(missing)
        score = completed * 20
        if counts["calculated_metrics"] > 0:
            score += 10
        if counts["claims"] > 0:
            score += 10
        if counts["documents"] == counts["facts"] == counts["claims"] == 0:
            health_status = "empty"
        elif review_required:
            health_status = "review_required"
        elif missing:
            health_status = "incomplete"
        else:
            health_status = "healthy"

        thesis_summary = None
        if thesis is not None:
            thesis_summary = {
                "id": thesis.id,
                "version": thesis.version,
                "status": thesis.status,
                "executive_summary": thesis.executive_summary,
                "rating": thesis.rating,
                "current_price": thesis.current_price,
                "bear_value": thesis.bear_value,
                "base_value": thesis.base_value,
                "bull_value": thesis.bull_value,
                "expected_value": thesis.expected_value,
                "margin_of_safety": thesis.margin_of_safety,
                "data_confidence_score": thesis.data_confidence_score,
                "source_coverage_score": thesis.source_coverage_score,
                "created_at": thesis.created_at,
            }

        model_summary = None
        if model is not None:
            model_summary = {
                "id": model.id,
                "version": model.version,
                "engine_version": model.engine_version,
                "algorithm_version": model.algorithm_version,
                "framework_key": model.framework_key,
                "horizon_years": model.horizon_years,
                "status": model.status,
                "publishable": model.publishable,
                "input_fingerprint": model.input_fingerprint,
                "forecast_fingerprint": model.forecast_fingerprint,
                "market_snapshot_fingerprint": model.market_snapshot_fingerprint,
                "valuation_snapshot_fingerprint": model.valuation_snapshot_fingerprint,
                "code_commit_sha": model.code_commit_sha,
                "scenario_probabilities": {
                    str(key): float(value) if value is not None else None
                    for key, value in (model.scenario_probabilities or {}).items()
                },
                "created_at": model.created_at,
            }

        return CompanySnapshotOut.model_validate(
            {
                "company": company,
                "latest_thesis": thesis_summary,
                "valuation_summary": {
                    "model_id": valuation_model.id if valuation_model else None,
                    "model_type": (
                        valuation_model.model_type
                        if valuation_model
                        else company.valuation_model
                    ),
                    "version": valuation_model.version if valuation_model else None,
                    "status": (
                        valuation_model.status if valuation_model else "not_generated"
                    ),
                    "current_price": thesis.current_price if thesis else None,
                    "bear_value": thesis.bear_value if thesis else None,
                    "base_value": thesis.base_value if thesis else None,
                    "bull_value": thesis.bull_value if thesis else None,
                    "expected_value": thesis.expected_value if thesis else None,
                    "margin_of_safety": thesis.margin_of_safety if thesis else None,
                    "updated_at": (
                        valuation_model.updated_at if valuation_model else None
                    ),
                },
                "model_summary": model_summary,
                "research_health": {
                    "score": min(100, score),
                    "status": health_status,
                    "missing": missing,
                    "review_required": review_required,
                },
                "counts": counts,
                "recent_changes": recent_changes,
            },
            from_attributes=True,
        )

    @staticmethod
    def _counts(db: Session, company_id: int) -> dict[str, int]:
        def count(model, *criteria) -> int:
            return int(db.scalar(select(func.count()).select_from(model).where(*criteria)) or 0)

        return {
            "facts": count(FinancialFact, FinancialFact.company_id == company_id),
            "calculated_metrics": count(
                CalculatedMetric, CalculatedMetric.company_id == company_id
            ),
            "documents": count(Document, Document.company_id == company_id),
            "claims": count(Claim, Claim.company_id == company_id),
            "thesis_versions": count(
                ThesisVersion, ThesisVersion.company_id == company_id
            ),
            "model_versions": count(
                FundamentalModelVersion,
                FundamentalModelVersion.company_id == company_id,
            ),
            "open_reviews": count(
                ResearchReview,
                ResearchReview.company_id == company_id,
                ResearchReview.status.in_(["open", "in_progress"]),
            ),
            "open_alerts": count(
                ResearchAlert,
                ResearchAlert.company_id == company_id,
                ResearchAlert.status.in_(["open", "snoozed"]),
            ),
        }
