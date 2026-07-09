import re
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import Company, ExternalClaim, NewsEvent, ThesisChange, ThesisVersion
from app.schemas import ManualNewsResponse, NewsFeedItem, NewsIngestResponse
from app.services.claim_intelligence_service import ClaimIntelligenceService
from app.services.materiality_service import MaterialityService
from app.services.review_alert_service import ReviewAlertService
from app.services.thesis_graph_service import ThesisGraphService


class NewsService:
    def __init__(self) -> None:
        self.materiality = MaterialityService()
        self.claim_intelligence = ClaimIntelligenceService()
        self.thesis_graph = ThesisGraphService()
        self.reviews = ReviewAlertService()

    def detect_ticker(self, db: Session, text: str) -> Company | None:
        tickers = {company.ticker: company for company in db.scalars(select(Company)).all()}
        upper_text = text.upper()
        for ticker, company in tickers.items():
            if re.search(rf"\b{re.escape(ticker)}\b", upper_text):
                return company
        return None

    def _company_for_item(self, db: Session, text: str, ticker: str | None = None) -> Company | None:
        if ticker:
            company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
            if company:
                return company
        return self.detect_ticker(db, text)

    def _is_duplicate(self, db: Session, company: Company | None, text: str, url: str | None) -> bool:
        if url:
            duplicate_url = db.scalar(select(NewsEvent.id).where(NewsEvent.url == url).limit(1))
            if duplicate_url:
                return True
        duplicate_title = db.scalar(
            select(NewsEvent.id)
            .where(
                NewsEvent.company_id == (company.id if company else None),
                NewsEvent.title == " ".join(text.strip().split())[:180],
            )
            .limit(1)
        )
        return duplicate_title is not None

    def _analyze_news(
        self,
        db: Session,
        text: str,
        source: str,
        url: str | None,
        ticker: str | None = None,
    ) -> ManualNewsResponse:
        company = self._company_for_item(db, text, ticker)
        assessment = self.materiality.assess_news(db, company, text, source, url)
        semantic_impact = (
            self.thesis_graph.assess_impact(
                db,
                company,
                text,
                base_materiality=assessment.materiality_score,
                impact_direction=assessment.impact_direction,
            )
            if company
            else None
        )
        materiality_score = (
            semantic_impact.impact_score
            if semantic_impact
            else assessment.materiality_score
        )
        requires_update = assessment.requires_update or bool(
            semantic_impact
            and semantic_impact.affected_claim_ids
            and materiality_score >= 7
        )

        summary = " ".join(text.strip().split())[:320]
        news = NewsEvent(
            company_id=company.id if company else None,
            date=datetime.now(UTC),
            title=summary[:180],
            source=source,
            url=url,
            summary=summary,
            event_type=assessment.event_type,
            materiality_score=materiality_score,
            impact_direction=assessment.impact_direction,
            affected_thesis=requires_update,
            affected_assumptions=assessment.affected_assumptions,
            requires_update=requires_update,
            processed_at=datetime.now(UTC),
        )
        db.add(news)
        db.flush()
        latest_thesis = None
        if company:
            latest_thesis = db.scalar(
                select(ThesisVersion)
                .where(ThesisVersion.company_id == company.id)
                .order_by(desc(ThesisVersion.version))
            )
        if requires_update and company:
            change_type = "news_material_update"
            if materiality_score >= 9 and assessment.impact_direction == "negative":
                change_type = "news_potential_invalidation"
            elif materiality_score >= 9 and assessment.impact_direction == "positive":
                change_type = "news_material_positive"
            change = ThesisChange(
                company_id=company.id,
                from_version_id=latest_thesis.id if latest_thesis else None,
                to_version_id=latest_thesis.id if latest_thesis else None,
                change_type=change_type,
                impact_direction=assessment.impact_direction,
                materiality_score=materiality_score,
                summary=(
                    f"Material news requires thesis review: {summary}. "
                    f"{semantic_impact.summary if semantic_impact else ''}"
                ).strip(),
                affected_claim_ids=(
                    semantic_impact.affected_claim_ids if semantic_impact else []
                ),
                affected_metrics=assessment.affected_assumptions,
                requires_review=True,
            )
            db.add(change)
            db.flush()
            self.reviews.create_from_news(db, news, change)
        db.add(
            ExternalClaim(
                company_id=company.id if company else None,
                source_id=None,
                claim=summary,
                claim_type="manual_news_claim",
                confidence=0.65,
                used_in_model=False,
            )
        )
        if company:
            self.claim_intelligence.scan_text(
                db,
                company=company,
                text=text,
                source_type=source,
                source_url=url,
                source_reference={"type": "news_event", "id": news.id},
                auto_apply=True,
            )
        else:
            db.commit()

        action = (
            "Actualizar tesis con aprobacion humana y filing/call si confirma el cambio."
            if requires_update
            else "Guardar en tracker; no tocar DCF hasta evidencia primaria."
        )
        return ManualNewsResponse(
            ticker=company.ticker if company else None,
            summary=summary,
            event_type=assessment.event_type,
            materiality_score=materiality_score,
            impact_direction=assessment.impact_direction,
            affected_thesis=requires_update,
            affected_assumptions=assessment.affected_assumptions,
            requires_update=requires_update,
            action=action,
            source_policy=assessment.source_policy,
            source_tier=assessment.source_tier,
            source_trust_score=assessment.source_trust_score,
            portfolio_weight=assessment.portfolio_weight,
            materiality_reasons=assessment.reasons,
            model_route=assessment.model_route,
            affected_claim_ids=(
                semantic_impact.affected_claim_ids if semantic_impact else []
            ),
            affected_node_ids=(
                semantic_impact.affected_node_ids if semantic_impact else []
            ),
            semantic_impact=(semantic_impact.trace if semantic_impact else {}),
        )

    def analyze_manual_news(self, db: Session, text: str, source: str, url: str | None) -> ManualNewsResponse:
        return self._analyze_news(db, text, source, url)

    def ingest_news_items(
        self,
        db: Session,
        items: list[NewsFeedItem],
        default_source: str = "feed",
    ) -> NewsIngestResponse:
        created_events: list[ManualNewsResponse] = []
        skipped_duplicates = 0

        for item in items:
            text = " ".join(part for part in [item.ticker, item.title, item.text] if part)
            company = self._company_for_item(db, text, item.ticker)
            if self._is_duplicate(db, company, text, item.url):
                skipped_duplicates += 1
                continue
            created_events.append(
                self._analyze_news(
                    db=db,
                    text=text,
                    source=item.source or default_source,
                    url=item.url,
                    ticker=item.ticker,
                )
            )

        return NewsIngestResponse(
            status="ingested",
            received=len(items),
            created=len(created_events),
            skipped_duplicates=skipped_duplicates,
            requires_update=sum(1 for event in created_events if event.requires_update),
            events=created_events,
        )
