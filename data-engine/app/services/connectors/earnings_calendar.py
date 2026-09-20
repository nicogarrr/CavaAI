"""Calendario publico de earnings y dividendos de NASDAQ.

Idea originada en ``s-kerin/finance_calendars`` (licencia permisiva MIT):
leer el calendario publico de NASDAQ (``api.nasdaq.com/api/calendar/...``)
dia a dia con ``httpx`` y tolerancia a fallos. Diseno inspirado en el,
implementacion propia para CavaAI: cliente asincrono inyectable en tests,
normalizacion minima de filas, fallo por dia registrado en ``errors`` sin
abortar el rango, y degradacion a ``None`` cuando un dia (o el servicio)
no responde: el llamante recibe ``status="unavailable"`` en lugar de una
excepcion.

No requiere API key, pero NASDAQ rechaza peticiones sin ``User-Agent`` de
navegador, de ahi las cabeceras por defecto.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import httpx

EARNINGS_URL = "https://api.nasdaq.com/api/calendar/earnings"
DIVIDENDS_URL = "https://api.nasdaq.com/api/calendar/dividends"

MAX_DAYS_PER_REQUEST = 31

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CavaAI/0.1) CavaAI Research",
    "Accept": "application/json",
}


def _parse_float(value: Any) -> float | None:
    if value in (None, "", "--", "N/A", "time-not-supplied"):
        return None
    try:
        return float(str(value).replace(",", "").strip("()%$"))
    except (TypeError, ValueError):
        return None


def normalize_earnings_row(row: dict[str, Any], day: date) -> dict[str, Any]:
    """Normaliza una fila del calendario de earnings a un evento propio."""
    return {
        "symbol": str(row.get("symbol", "")).upper(),
        "company": row.get("name"),
        "date": day.isoformat(),
        "time": row.get("time"),
        "eps_forecast": _parse_float(row.get("epsForecast")),
        "n_estimates": _parse_float(row.get("noOfEsts")),
        "fiscal_quarter_ending": row.get("fiscalQuarterEnding"),
        "market_cap": _parse_float(row.get("marketCap")),
    }


def normalize_dividend_row(row: dict[str, Any], day: date) -> dict[str, Any]:
    """Normaliza una fila del calendario de dividendos a un evento propio."""
    return {
        "symbol": str(row.get("symbol", "")).upper(),
        "company": row.get("companyName") or row.get("name"),
        "date": day.isoformat(),
        "ex_date": row.get("dividend_Ex_Date"),
        "payment_date": row.get("payment_Date"),
        "record_date": row.get("record_Date"),
        "amount": _parse_float(row.get("dividend_Rate") or row.get("amount")),
    }


async def _get_json(
    url: str,
    params: dict[str, str],
    client: httpx.AsyncClient | None,
) -> dict | None:
    """GET con degradacion a None ante cualquier fallo de red o parseo."""
    if client is not None:
        try:
            response = await client.get(url, params=params, headers=BROWSER_HEADERS)
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, dict) else None
        except Exception:  # noqa: BLE001 — el calendario nunca debe romper el flujo
            return None
    try:
        async with httpx.AsyncClient(timeout=20, headers=BROWSER_HEADERS) as owned:
            response = await owned.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, dict) else None
    except Exception:  # noqa: BLE001 — ver nota anterior
        return None


async def fetch_earnings_day(
    day: date,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]] | None:
    """Eventos de earnings de un dia, o None si NASDAQ no responde."""
    payload = await _get_json(EARNINGS_URL, {"date": day.isoformat()}, client)
    if not payload:
        return None
    data = payload.get("data") or {}
    rows = data.get("rows") or []
    events = [normalize_earnings_row(row, day) for row in rows if row.get("symbol")]
    return events


async def fetch_dividends_day(
    day: date,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]] | None:
    """Eventos de dividendos de un dia, o None si NASDAQ no responde."""
    payload = await _get_json(DIVIDENDS_URL, {"date": day.isoformat()}, client)
    if not payload:
        return None
    data = payload.get("data") or {}
    calendar = data.get("calendar") or data
    rows = calendar.get("rows") or []
    return [normalize_dividend_row(row, day) for row in rows if row.get("symbol")]


def _check_range(desde: date, hasta: date) -> None:
    if desde > hasta:
        raise ValueError("desde no puede ser posterior a hasta")
    if (hasta - desde).days + 1 > MAX_DAYS_PER_REQUEST:
        raise ValueError(f"rango maximo: {MAX_DAYS_PER_REQUEST} dias")


async def fetch_earnings_range(
    desde: date,
    hasta: date,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Agrega earnings dia a dia; los dias que fallan van a ``errors``.

    Si ningun dia responde, ``status`` es ``"unavailable"`` y ``events`` es
    ``[]``; si solo fallan algunos, ``status`` es ``"partial"``.
    """
    _check_range(desde, hasta)
    events: list[dict[str, Any]] = []
    errors: list[str] = []
    current = desde
    while current <= hasta:
        day_events = await fetch_earnings_day(current, client)
        if day_events is None:
            errors.append(f"{current.isoformat()}: calendario no disponible")
        else:
            events.extend(day_events)
        current += timedelta(days=1)
    if errors and not events:
        status = "unavailable"
    elif errors:
        status = "partial"
    else:
        status = "ok"
    return {
        "status": status,
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "count": len(events),
        "events": events,
        "errors": errors,
    }


async def fetch_dividends_range(
    desde: date,
    hasta: date,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Agrega dividendos dia a dia con la misma semantica de degradacion."""
    _check_range(desde, hasta)
    events: list[dict[str, Any]] = []
    errors: list[str] = []
    current = desde
    while current <= hasta:
        day_events = await fetch_dividends_day(current, client)
        if day_events is None:
            errors.append(f"{current.isoformat()}: calendario no disponible")
        else:
            events.extend(day_events)
        current += timedelta(days=1)
    if errors and not events:
        status = "unavailable"
    elif errors:
        status = "partial"
    else:
        status = "ok"
    return {
        "status": status,
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "count": len(events),
        "events": events,
        "errors": errors,
    }
