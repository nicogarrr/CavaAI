from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Claim,
    Company,
    EvidenceSuggestion,
    FinancialFact,
    MemoryItem,
    ResearchAlert,
    ResearchReview,
    ThesisChange,
    ThesisSection,
    ThesisVersion,
)
from app.schemas import (
    ClaimOut,
    CompanyOut,
    EvidenceSuggestionOut,
    FinancialFactOut,
    MemoryItemOut,
    ResearchAlertOut,
    ResearchReviewOut,
    ThesisChangeOut,
    ThesisGraphOut,
    ThesisOut,
    ThesisSectionOut,
)
from app.services.fundamental_review_service import (
    DecisionJournalService,
    ExpectationRealityService,
)
from app.services.long_term_model_service import LongTermModelService
from app.services.metric_calculation_service import MetricCalculationService
from app.services.moat_service import MoatService
from app.services.peer_analysis_service import PeerAnalysisService
from app.services.peer_comparison_service import PeerComparisonService
from app.services.red_team_service import RedTeamService
from app.services.thesis_graph_service import ThesisGraphService
from app.services.valuation_service import ValuationService


def _dump(schema: type[BaseModel], value):
    return schema.model_validate(value).model_dump(mode="json", by_alias=True)


class CompanySnapshotService:
    """One coherent API snapshot for the company workspace."""

    def build(self, db: Session, company: Company, horizon: int = 5) -> dict:
        # Local imports avoid coupling the route registry at application startup.
        from app.api.routes.companies import (
            _decision_payload,
            _expectation_payload,
            _red_team_payload,
        )
        from app.api.routes.sources import documents as source_documents

        valuation = ValuationService().value_company(db, company)
        financial_facts = list(
            db.scalars(
                select(FinancialFact)
                .where(FinancialFact.company_id == company.id)
                .order_by(
                    FinancialFact.fiscal_year.desc().nullslast(),
                    desc(FinancialFact.created_at),
                )
                .limit(80)
            ).all()
        )
        metrics = MetricCalculationService().calculate_all(db, company, persist=True)
        long_term = LongTermModelService().build(db, company, horizon=horizon)
        thesis_history = list(
            db.scalars(
                select(ThesisVersion)
                .where(ThesisVersion.company_id == company.id)
                .order_by(desc(ThesisVersion.version))
                .limit(50)
            ).all()
        )
        thesis = thesis_history[0] if thesis_history else None

        claims = list(
            db.scalars(
                select(Claim)
                .options(selectinload(Claim.evidence))
                .where(Claim.company_id == company.id)
                .order_by(desc(Claim.created_at))
                .limit(20)
            ).all()
        )
        thesis_sections: list[ThesisSection] = []
        thesis_changes: list[ThesisChange] = []
        graph = None
        if thesis:
            thesis_sections = list(
                db.scalars(
                    select(ThesisSection)
                    .where(ThesisSection.thesis_version_id == thesis.id)
                    .order_by(ThesisSection.order_index, ThesisSection.section_key)
                ).all()
            )
            try:
                graph_thesis, nodes, edges = ThesisGraphService().build(db, company, thesis)
                graph = _dump(
                    ThesisGraphOut,
                    {"ticker": company.ticker, "thesis_version_id": graph_thesis.id, "nodes": nodes, "edges": edges},
                )
            except ValueError:
                graph = None
        thesis_changes = list(
            db.scalars(
                select(ThesisChange)
                .where(ThesisChange.company_id == company.id)
                .order_by(desc(ThesisChange.created_at))
                .limit(50)
            ).all()
        )
        reviews = list(
            db.scalars(
                select(ResearchReview)
                .where(ResearchReview.company_id == company.id, ResearchReview.status == "open")
                .order_by(desc(ResearchReview.created_at))
                .limit(100)
            ).all()
        )
        alerts = list(
            db.scalars(
                select(ResearchAlert)
                .where(ResearchAlert.company_id == company.id)
                .order_by(desc(ResearchAlert.created_at))
                .limit(100)
            ).all()
        )
        memory_items = list(
            db.scalars(
                select(MemoryItem)
                .where(MemoryItem.company_id == company.id, MemoryItem.scope == "company")
                .order_by(desc(MemoryItem.created_at))
                .limit(20)
            ).all()
        )
        suggestions = list(
            db.scalars(
                select(EvidenceSuggestion)
                .where(EvidenceSuggestion.company_id == company.id, EvidenceSuggestion.status == "pending")
                .order_by(desc(EvidenceSuggestion.confidence), desc(EvidenceSuggestion.created_at))
                .limit(100)
            ).all()
        )
        red_team = RedTeamService().latest(db, company)

        return {
            "company": _dump(CompanyOut, company),
            "valuation": valuation,
            "facts": [_dump(FinancialFactOut, fact) for fact in financial_facts],
            "calculatedMetrics": [
                {
                    "id": metric.id,
                    "company_id": company.id,
                    "metric": metric.metric,
                    "value": metric.value,
                    "unit": metric.unit,
                    "period": metric.period,
                    "fiscal_year": metric.fiscal_year,
                    "fiscal_quarter": metric.fiscal_quarter,
                    "status": metric.status,
                    "definition_version": metric.definition_version,
                    "formula": metric.formula,
                    "numerator": metric.numerator,
                    "denominator": metric.denominator,
                    "source_fact_ids": metric.source_fact_ids,
                    "calculation_trace": metric.calculation_trace,
                    "confidence": metric.confidence,
                }
                for metric in metrics
            ],
            "peerComparison": PeerComparisonService().compare(db, company, limit=8, refresh=False),
            "peerAnalysis": PeerAnalysisService().analyze(db, company, limit=8),
            "moat": MoatService().assess(db, company, persist=True),
            "thesis": _dump(ThesisOut, thesis) if thesis else None,
            "thesisHistory": [_dump(ThesisOut, version) for version in thesis_history],
            "claims": [_dump(ClaimOut, claim) for claim in claims],
            "thesisSections": [_dump(ThesisSectionOut, section) for section in thesis_sections],
            "thesisChanges": [_dump(ThesisChangeOut, change) for change in thesis_changes],
            "thesisGraph": graph,
            "reviews": [_dump(ResearchReviewOut, review) for review in reviews],
            "alerts": [_dump(ResearchAlertOut, alert) for alert in alerts],
            "memoryItems": [_dump(MemoryItemOut, item) for item in memory_items],
            "sourceDocuments": source_documents(
                ticker=company.ticker,
                include_chunks=True,
                chunk_limit=1000,
                chunk_text_limit=1800,
                db=db,
            ),
            "evidenceSuggestions": [_dump(EvidenceSuggestionOut, item) for item in suggestions],
            "redTeam": _red_team_payload(red_team) if red_team else None,
            "longTermModel": long_term,
            "decisionJournal": [
                _decision_payload(entry) for entry in DecisionJournalService().list(db, company)
            ],
            "expectationReviews": [
                _expectation_payload(item) for item in ExpectationRealityService().list(db, company)
            ],
        }
