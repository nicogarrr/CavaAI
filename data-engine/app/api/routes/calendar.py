"""Calendario de mercado (earnings y dividendos via NASDAQ publico)."""

from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query

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
