from fastapi import APIRouter, Depends
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Company, NewsEvent
from app.schemas import ManualNewsRequest, ManualNewsResponse, NewsIngestRequest, NewsIngestResponse
from app.services.materiality_service import MaterialityService
from app.services.news_service import NewsService

router = APIRouter()


@router.post("/manual", response_model=ManualNewsResponse)
def manual_news(payload: ManualNewsRequest, db: Session = Depends(get_db)) -> ManualNewsResponse:
    return NewsService().analyze_manual_news(db, payload.text, payload.source, payload.url)


@router.post("/ingest", response_model=NewsIngestResponse)
def ingest_news(payload: NewsIngestRequest, db: Session = Depends(get_db)) -> NewsIngestResponse:
    return NewsService().ingest_news_items(db, payload.items, payload.source)


@router.get("")
def news_events(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        select(NewsEvent, Company)
        .outerjoin(Company, NewsEvent.company_id == Company.id)
        .order_by(desc(NewsEvent.date))
        .limit(100)
    ).all()
    materiality = MaterialityService()
    events = []
    for event, company in rows:
        assessment = materiality.assess_news(db, company, event.summary or event.title, event.source, event.url)
        events.append(
            {
                "id": event.id,
                "ticker": company.ticker if company else None,
                "date": event.date.isoformat(),
                "title": event.title,
                "source": event.source,
                "url": event.url,
                "event_type": event.event_type,
                "materiality_score": event.materiality_score,
                "impact_direction": event.impact_direction,
                "requires_update": event.requires_update,
                "source_tier": assessment.source_tier,
                "source_trust_score": assessment.source_trust_score,
                "portfolio_weight": assessment.portfolio_weight,
                "materiality_reasons": assessment.reasons,
                "source_policy": assessment.source_policy,
                "model_route": assessment.model_route,
            }
        )
    return events
