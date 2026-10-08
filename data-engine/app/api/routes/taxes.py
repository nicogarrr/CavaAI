"""Fiscal-year tax reports (IRPF-style) for the private portfolio."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.tax_modelo720_file import Modelo720FileService
from app.services.tax_modelo720_service import Modelo720Service
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

@router.get("/modelo720/{fiscal_year}/thresholds")
def modelo720_thresholds(fiscal_year: int, db: Session = Depends(get_db)) -> dict:
    """Chequeo de umbrales del Modelo 720 (50.000 EUR por categoria).

    Solo lectura. Chequeo orientativo con estados sin-datos honestos; no es
    la declaracion ni prueba la obligacion por si solo.
    """
    _validate_year(fiscal_year)
    return Modelo720Service().check_thresholds(db, fiscal_year)


@router.get("/modelo720/{fiscal_year}/file")
def modelo720_file(fiscal_year: int, db: Session = Depends(get_db)) -> dict:
    """Fichero del Modelo 720 (500 bytes/registro, spec oficial AEAT).

    Solo lectura. Requiere los datos del declarante en la metadata del
    tenant (clave 'tax_declarant'); sin ellos devuelve available=false con
    el motivo. AYUDA DE CÓMPUTO: revisar antes de presentar por TGVI Online.
    """
    _validate_year(fiscal_year)
    return Modelo720FileService().generate(db, fiscal_year)


class FilingPreviewInput(BaseModel):
    # TME copiado del borrador del usuario, en porcentaje (19,00 -> 0,19).
    # No se persiste ni se aplica a otro ejercicio/tenant.
    tme_percent: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2)


@router.post("/report/{fiscal_year}/preview")
def preview_tax_filing(
    fiscal_year: int,
    inputs: FilingPreviewInput,
    db: Session = Depends(get_db),
) -> dict:
    """Vista previa IRPF con TME manual. Solo cálculo, sin guardar datos."""
    _validate_year(fiscal_year)
    try:
        return TaxReportService().get_report(
            db, fiscal_year, tme=inputs.tme_percent / Decimal("100")
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
