"""Inversores: tabla fija + resumen de cartera 13F (solo gestores revisados)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.investor_videos import investor_videos
from app.services.investors import investor_detail, list_investors, most_bought
from app.services.manager_holding_ingestion_service import ManagerHoldingIngestionService

router = APIRouter()


@router.get("")
def investors(db: Session = Depends(get_db)) -> dict:
    """Lista de inversores con resumen de su ultimo 13F (o 'Sin datos')."""
    return list_investors(db)


@router.get("/most-bought")
def most_bought_route(db: Session = Depends(get_db)) -> dict:
    """Acciones mas compradas por los gestores revisados (13F, trimestre vs anterior)."""
    return most_bought(db)


@router.get("/{slug}")
def investor(slug: str, db: Session = Depends(get_db)) -> dict:
    """Ficha de un inversor: posiciones del ultimo 13F y cambios trimestrales."""
    detail = investor_detail(db, slug)
    if detail is None:
        raise HTTPException(status_code=404, detail="investor not found")
    if detail["cik"]:
        detail["changes"] = ManagerHoldingIngestionService().changes(db, cik=detail["cik"])
    detail["videos"] = investor_videos(slug)
    return detail
