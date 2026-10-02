"""D3: qué pasó con la tesis. Lectura y recálculo idempotente.

Respuestas en español. Cada cifra ausente sale ``N/D`` con su motivo, y el
agregado enseña el denominador del hit-rate y los casos excluidos: un
hit-rate sin el denominador ni los inconclusos es propaganda.

El recálculo es síncrono a propósito: son un puñado de consultas sobre precios
ya persistidos, sin red y sin LLM, así que no hay nada que Durable. Un
recálculo de tesis no se encola a un worker para que un número que cabe en
seis queries tarde un minuto en volver.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import ThesisVersion
from app.services.company_resolver import resolve_company
from app.services.thesis_realized_return_service import (
    N_D,
    OUTCOME_DEFINITIONS,
    ThesisRealizedReturnService,
    realized_return_payload,
)

router = APIRouter()


class RecomputeRequest(BaseModel):
    """Recálculo idempotente: sin `ticker` va a todas las tesis del tenant."""

    ticker: str | None = Field(default=None, max_length=20)
    limit: int = Field(default=200, ge=1, le=1000)


@router.get("")
def realized_return_by_ticker(
    ticker: str = Query(min_length=1, max_length=20),
    db: Session = Depends(get_db),
) -> dict:
    """Todas las versiones de tesis del ticker con su retorno realizado."""
    company = resolve_company(db, ticker)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    service = ThesisRealizedReturnService()
    rows = service.for_company(db, company.id)
    if not rows:
        raise HTTPException(
            status_code=404,
            detail=(
                "No hay retorno realizado calculado para este ticker; ejecute el "
                "recálculo primero"
            ),
        )
    return {
        "ticker": company.ticker,
        "empresa": company.name,
        "divisa": company.currency or N_D,
        "casos": len(rows),
        "resultados": [realized_return_payload(row) for row in rows],
        "definiciones_veredicto": OUTCOME_DEFINITIONS,
    }


@router.get("/portfolio")
def realized_return_portfolio(db: Session = Depends(get_db)) -> dict:
    """Agregado global: hit-rate con denominador, retornos, alfa y dispersión."""
    return ThesisRealizedReturnService().portfolio_summary(db)


@router.get("/{thesis_id}")
def realized_return_by_thesis(thesis_id: int, db: Session = Depends(get_db)) -> dict:
    """El retorno realizado de una versión de tesis concreta."""
    row = ThesisRealizedReturnService().for_thesis(db, thesis_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No hay retorno realizado para esa tesis")
    return realized_return_payload(row)


@router.post("/recompute")
def recompute_realized_return(
    payload: RecomputeRequest, db: Session = Depends(get_db)
) -> dict:
    """Recalcula idempotentemente. Repetir no duplica ni reescribe un cierre."""
    service = ThesisRealizedReturnService()
    if payload.ticker:
        company = resolve_company(db, payload.ticker)
        if company is None:
            raise HTTPException(status_code=404, detail="Company not found")
        rows: list[dict] = []
        actualizados = 0
        for thesis in db.scalars(
            select(ThesisVersion)
            .where(ThesisVersion.company_id == company.id)
            .order_by(ThesisVersion.version)
        ).all():
            row, changed = service.persist(db, company, thesis)
            rows.append(realized_return_payload(row))
            actualizados += int(changed)
        if not rows:
            raise HTTPException(
                status_code=404, detail="El ticker no tiene ninguna versión de tesis"
            )
        return {
            "ticker": company.ticker,
            "recomputados": len(rows),
            "actualizados": actualizados,
            "sin_cambios": len(rows) - actualizados,
            "resultados": rows,
        }
    stats = service.recompute_portfolio(db, limit=payload.limit)
    return {
        "ambito": "todas las tesis del tenant",
        **stats,
        "agregado": service.portfolio_summary(db),
    }
