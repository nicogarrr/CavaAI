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
    db: Session = Depends(get_db),
) -> dict:
    """Informe fiscal de un ejercicio. Solo lectura.

    Antes aceptaba `?regenerate=true`, que ademas de persistir un TaxReport
    (una escritura) hacia que un GET tuviera efectos de estado: no idempotente,
    imposible de cachear y capaz de devolver 500 en un camino de lectura. El
    calculo forzado vive en POST /report/{fiscal_year}/regenerate, que ya
    existe; este handler usa `get_report`, que devuelve el informe persistido
    o lo calcula EN MEMORIA sin escribir (`persisted=False`).
    """
    _validate_year(fiscal_year)
    try:
        return TaxReportService().get_report(db, fiscal_year)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _validate_year(fiscal_year: int) -> None:
    if fiscal_year < 2000 or fiscal_year > 2200:
        raise HTTPException(
            status_code=400, detail="fiscal_year must be between 2000 and 2200"
        )


@router.get("/holdings")
def tax_holdings(db: Session = Depends(get_db)) -> list[dict]:
    return build_tax_summary_rows(db)


@router.post("/report/{fiscal_year}/regenerate")
def regenerate_tax_report(fiscal_year: int, db: Session = Depends(get_db)) -> dict:
    _validate_year(fiscal_year)
    try:
        return TaxReportService().regenerate_report(db, fiscal_year)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc