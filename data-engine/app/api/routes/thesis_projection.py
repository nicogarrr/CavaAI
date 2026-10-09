"""Proyeccion de tesis a 5 ejercicios: calculo determinista, sin LLM (PR A)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.company_resolver import resolve_company
from app.services.thesis_projection_service import (
    ProjectionQuotaExceeded,
    ThesisProjectionService,
)

router = APIRouter()


@router.get("/{ticker}/thesis-5y")
def get_thesis_5y(ticker: str, db: Session = Depends(get_db)) -> dict:
    """Proyeccion actual bear/base/bull con etiquetas, fuentes y fechas.

    Es calculo puro sobre lo persistido (no consume cuota ni escribe); el
    bloque ``persistido`` apunta a la ultima version guardada via POST.
    """
    company = resolve_company(db, ticker)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    service = ThesisProjectionService()
    payload = service.project(db, company)
    payload["persistido"] = service.latest_persisted(db, company)
    return payload


@router.post("/{ticker}/thesis-5y/recalcular", status_code=201)
def recalcular_thesis_5y(ticker: str, db: Session = Depends(get_db)) -> dict:
    """Recalcula y persiste la proyeccion. Cuota diaria por tenant, serializada."""
    company = resolve_company(db, ticker)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    if db.info.get("tenant_id") is None:
        raise HTTPException(status_code=403, detail="Tenant context required")
    service = ThesisProjectionService()
    try:
        payload, model = service.recalculate_within_quota(db, company)
    except ProjectionQuotaExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    payload["persistido"] = {
        "valuation_model_id": model.id,
        "version": model.version,
        "status": model.status,
        "created_at": model.created_at.isoformat() if model.created_at else None,
    }
    return payload
