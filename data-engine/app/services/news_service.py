import re
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import Company, ExternalClaim, NewsEvent, ThesisChange, ThesisVersion
from app.schemas import ManualNewsResponse, NewsFeedItem, NewsIngestResponse

MATERIAL_KEYWORDS = {
    "dilution": ["offering", "dilution", "atm", "capital raise", "convertible", "shares"],
    "earnings": ["earnings", "guidance", "revenue", "eps", "fcf", "margin"],
    "regulatory": ["fda", "sec", "fcc", "ema", "regulatory", "investigation", "approval"],
    "contract": ["contract", "award", "customer", "backlog", "launch", "partnership"],
    "capital_allocation": ["buyback", "repurchase", "dividend", "spin-off", "asset sale"],
}


class NewsService:
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
        lower_text = text.lower()
        matched_types = [
            event_type
            for event_type, keywords in MATERIAL_KEYWORDS.items()
            if any(keyword in lower_text for keyword in keywords)
        ]
        event_type = matched_types[0] if matched_types else "general_news"

        materiality = 3
        if matched_types:
            materiality += 2 * len(matched_types)
        if "dilution" in matched_types:
            materiality += 2
        if any(word in lower_text for word in ["bankruptcy", "fraud", "halt", "default"]):
            materiality = 10
        if company and ("pre_fcf" in company.factor_tags or "speculative" in company.factor_tags):
            materiality += 1
        materiality = max(1, min(materiality, 10))

        affected_assumptions = []
        if "dilution" in matched_types:
            affected_assumptions.extend(["share_count", "cash_runway", "dilution_risk"])
        if "earnings" in matched_types:
            affected_assumptions.extend(["revenue_growth", "fcf_margin", "guidance"])
        if "regulatory" in matched_types:
            affected_assumptions.extend(["approval_probability", "regulatory_risk"])
        if "contract" in matched_types:
            affected_assumptions.extend(["revenue_timing", "backlog_conversion"])
        if "capital_allocation" in matched_types:
            affected_assumptions.extend(["share_count", "capital_allocation"])

        requires_update = materiality >= 7
        impact_direction = "neutral"
        if any(word in lower_text for word in ["beat", "approval", "award", "buyback", "raise"]):
            impact_direction = "positive"
        if any(word in lower_text for word in ["miss", "cut", "delay", "offering", "investigation"]):
            impact_direction = "negative"

        summary = " ".join(text.strip().split())[:320]
        news = NewsEvent(
            company_id=company.id if company else None,
            date=datetime.now(UTC),
            title=summary[:180],
            source=source,
            url=url,
            summary=summary,
            event_type=event_type,
            materiality_score=materiality,
            impact_direction=impact_direction,
            affected_thesis=requires_update,
            affected_assumptions=sorted(set(affected_assumptions)),
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
            if materiality >= 9 and impact_direction == "negative":
                change_type = "news_potential_invalidation"
            elif materiality >= 9 and impact_direction == "positive":
                change_type = "news_material_positive"
            db.add(
                ThesisChange(
                    company_id=company.id,
                    from_version_id=latest_thesis.id if latest_thesis else None,
                    to_version_id=latest_thesis.id if latest_thesis else None,
                    change_type=change_type,
                    impact_direction=impact_direction,
                    materiality_score=materiality,
                    summary=f"Material news requires thesis review: {summary}",
                    affected_claim_ids=[],
                    affected_metrics=sorted(set(affected_assumptions)),
                    requires_review=True,
                )
            )
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
        db.commit()

        action = (
            "Actualizar tesis con aprobacion humana y filing/call si confirma el cambio."
            if requires_update
            else "Guardar en tracker; no tocar DCF hasta evidencia primaria."
        )
        return ManualNewsResponse(
            ticker=company.ticker if company else None,
            summary=summary,
            event_type=event_type,
            materiality_score=materiality,
            impact_direction=impact_direction,
            affected_thesis=requires_update,
            affected_assumptions=sorted(set(affected_assumptions)),
            requires_update=requires_update,
            action=action,
            source_policy="Manual input is evidence, not official truth; material model changes require primary-source confirmation.",
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
