from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Company
from app.services.work_product_service import WorkProductService


router = APIRouter()


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
        raise HTTPException(status_code=400, detail=str(exc)) from exc
