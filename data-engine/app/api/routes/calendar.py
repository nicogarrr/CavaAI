"""Calendario de mercado (earnings, dividendos y catalizadores de cartera)."""

import asyncio
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services import catalyst_calendar_service as catalyst_service
from app.services.connectors import earnings_calendar as calendar_connector

router = APIRouter()


def _resolve_range(desde: date | None, hasta: date | None) -> tuple[date, date]:
    start = desde or date.today()
    end = hasta or (start + timedelta(days=7))
    if start > end:
        raise HTTPException(status_code=400, detail="desde no puede ser posterior a hasta")
    if (end - start).days + 1 > calendar_connector.MAX_DAYS_PER_REQUEST:
        raise HTTPException(
            status_code=400,
            detail=f"rango maximo: {calendar_connector.MAX_DAYS_PER_REQUEST} dias",
        )
    return start, end


@router.get("/earnings")
async def earnings_calendar(
    desde: date | None = Query(default=None),
    hasta: date | None = Query(default=None),
) -> dict:
    """Eventos de earnings entre ``desde`` y ``hasta`` (por defecto, 7 dias).

    El conector degrada a ``status="unavailable"`` si NASDAQ no responde;
    este endpoint nunca devuelve 5xx por un fallo del proveedor.
    """
    start, end = _resolve_range(desde, hasta)
    try:
        return await calendar_connector.fetch_earnings_range(start, end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/dividends")
async def dividends_calendar(
    desde: date | None = Query(default=None),
    hasta: date | None = Query(default=None),
) -> dict:
    """Eventos de dividendos entre ``desde`` y ``hasta`` (por defecto, 7 dias)."""
    start, end = _resolve_range(desde, hasta)
    try:
        return await calendar_connector.fetch_dividends_range(start, end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/catalysts")
async def catalysts_calendar(
    desde: date | None = Query(default=None),
    hasta: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """Calendario unico de catalizadores de la cartera (por defecto, 14 dias).

    Une resultados y dividendos (NASDAQ publico, solo empresas con posicion
    abierta) y acciones corporativas registradas sin aplicar. Si NASDAQ no
    responde, ``status`` lo declara (``partial``/``unavailable``) y las
    acciones corporativas propias se siguen mostrando; nunca devuelve 5xx
    por un fallo del proveedor.
    """
    start = desde or date.today()
    end = hasta or (start + timedelta(days=14))
    start, end = _resolve_range(start, end)
    held = catalyst_service.held_tickers(db)
    if not held:
        return {
            "status": "ok",
            "desde": start.isoformat(),
            "hasta": end.isoformat(),
            "held_count": 0,
            "count": 0,
            "events": [],
            "errors": [],
        }
    earnings, dividends = await asyncio.gather(
        calendar_connector.fetch_earnings_range(start, end),
        calendar_connector.fetch_dividends_range(start, end),
    )
    events = catalyst_service.build_catalysts(
        held=held,
        desde=start,
        hasta=end,
        earnings=earnings["events"],
        dividends=dividends["events"],
        actions=catalyst_service.pending_actions(db, start, end),
    )
    return {
        "status": catalyst_service.combine_status(earnings["status"], dividends["status"]),
        "desde": start.isoformat(),
        "hasta": end.isoformat(),
        "held_count": len(held),
        "count": len(events),
        "events": events,
        "errors": earnings["errors"] + dividends["errors"],
    }
