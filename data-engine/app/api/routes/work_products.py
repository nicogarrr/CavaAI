import logging
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Company
from app.services.work_product_service import WorkProductService


router = APIRouter()

_logger = logging.getLogger(__name__)


class WorkProductRequest(BaseModel):
    product_type: Literal[
        "one_page_memo",
        "full_thesis",
        "earnings_review",
        "valuation_memo",
        "capital_allocation_analysis",
        "comparables",
        "portfolio_review",
        "risk_report",
    ]
    ticker: str | None = Field(default=None, max_length=20)
    years: int = Field(default=10, ge=1, le=20)


@router.post("/generate")
def generate_work_product(
    payload: WorkProductRequest, db: Session = Depends(get_db)
) -> dict:
    company = None
    if payload.ticker:
        company = db.scalar(
            select(Company).where(Company.ticker == payload.ticker.upper())
        )
        if company is None:
            raise HTTPException(status_code=404, detail="Company not found")
    try:
        return WorkProductService().generate(
            db,
            product_type=payload.product_type,
            company=company,
            years=payload.years,
        )
    except ValueError as exc:
        # Sin filtrar internos: ticker desconocido → 404 fijo, resto → 400
        # genérico con referencia logueada.
        if "unknown ticker" in str(exc).lower():
            raise HTTPException(status_code=404, detail="Company not found") from exc
        ref = uuid4().hex[:8]
        _logger.exception("work product generation failed (ref=%s)", ref)
        raise HTTPException(
            status_code=400, detail=f"Work product generation failed (ref {ref})"
        ) from exc
    except Exception as exc:
        ref = uuid4().hex[:8]
        _logger.exception("work product generation failed (ref=%s)", ref)
        raise HTTPException(
            status_code=500, detail=f"Work product generation failed (ref {ref})"
        ) from exc
