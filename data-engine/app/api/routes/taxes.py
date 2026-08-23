"""Fiscal-year tax reports (IRPF-style) for the private portfolio."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.tax_report_service import TaxReportService, build_tax_summary_rows

router = APIRouter()


@router.get("/report/{fiscal_year}")
def tax_report(
    fiscal_year: int,
    regenerate: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict:
    if fiscal_year < 2000 or fiscal_year > 2200:
        raise HTTPException(status_code=400, detail="fiscal_year must be between 2000 and 2200")
    try:
        return TaxReportService().get_or_compute(db, fiscal_year, regenerate=regenerate)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/holdings")
def tax_holdings(db: Session = Depends(get_db)) -> list[dict]:
    return build_tax_summary_rows(db)


class TaxReportInput(BaseModel):
    fiscal_year: int = Field(ge=2000, le=2200)


@router.post("/report/{fiscal_year}/regenerate")
def regenerate_tax_report(fiscal_year: int, db: Session = Depends(get_db)) -> dict:
    if fiscal_year < 2000 or fiscal_year > 2200:
        raise HTTPException(status_code=400, detail="fiscal_year must be between 2000 and 2200")
    try:
        return TaxReportService().get_or_compute(db, fiscal_year, regenerate=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc