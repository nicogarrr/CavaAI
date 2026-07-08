from fastapi import APIRouter, Depends
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Company, NewsEvent
from app.schemas import ManualNewsRequest, ManualNewsResponse
from app.services.news_service import NewsService

router = APIRouter()


@router.post("/manual", response_model=ManualNewsResponse)
def manual_news(payload: ManualNewsRequest, db: Session = Depends(get_db)) -> ManualNewsResponse:
    return NewsService().analyze_manual_news(db, payload.text, payload.source, payload.url)


@router.get("")
def news_events(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        select(NewsEvent, Company)
        .outerjoin(Company, NewsEvent.company_id == Company.id)
        .order_by(desc(NewsEvent.date))
        .limit(100)
    ).all()
    return [
        {
            "id": event.id,
            "ticker": company.ticker if company else None,
            "date": event.date.isoformat(),
            "title": event.title,
            "source": event.source,
            "event_type": event.event_type,
            "materiality_score": event.materiality_score,
            "impact_direction": event.impact_direction,
            "requires_update": event.requires_update,
        }
        for event, company in rows
    ]

