from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Company, NewsEvent
from app.schemas import ManualNewsRequest, ManualNewsResponse, NewsIngestRequest, NewsIngestResponse
from app.services.news_service import NewsService
from app.services.second_order_news_service import analyze_second_order

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
    events = []
    for event, company in rows:
        # Solo lo persistido en ingesta (F314): recomputar por peticion
        # costaba una evaluacion por noticia y podia divergir de lo
        # persistido. Eventos legacy sin assessment persistido -> nulls
        # honestos (la UI los muestra como N/D).
        persisted = (event.metadata_ or {}).get("assessment") or {}
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
                "date_source": (event.metadata_ or {}).get("date_source"),
                # False solo en titulares de display generados por CavaAI
                # (ausente en filas legacy = titular real de la fuente).
                "headline_from_source": (event.metadata_ or {}).get("headline_from_source", True),
                # Carril macro GDELT (#564): None en eventos de empresa.
                "news_lane": (event.metadata_ or {}).get("news_lane"),
                "macro_theme": (event.metadata_ or {}).get("macro_theme"),
                "source_tier": persisted.get("source_tier"),
                "source_trust_score": persisted.get("source_trust_score"),
                "portfolio_weight": persisted.get("portfolio_weight"),
                "materiality_reasons": persisted.get("materiality_reasons"),
                "source_policy": persisted.get("source_policy"),
                "model_route": persisted.get("model_route"),
            }
        )
    return events


@router.get("/{event_id}/second-order")
def second_order_hypotheses(
    event_id: int,
    use_llm: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict:
    event = db.get(NewsEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Noticia no encontrada")
    return analyze_second_order(db, event, use_llm=use_llm)
