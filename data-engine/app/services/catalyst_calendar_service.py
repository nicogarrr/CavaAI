"""Calendario unico de catalizadores de la cartera.

Une, para las empresas con posicion abierta (quantity > 0), tres fuentes que
hasta ahora vivian en pantallas distintas:

* resultados (earnings) del calendario publico de NASDAQ,
* fecha ex-dividendo del mismo calendario,
* acciones corporativas registradas en CavaAI (splits, etc.) aun no aplicadas.

Cobertura declarada: el calendario de dividendos de NASDAQ se consulta por dia
y solo devuelve las filas cuya fecha ex-dividendo cae en ese dia, por eso el
calendario muestra la fecha ex y NO la fecha de pago (un pago cuyo ex-date fue
anterior al rango no aparecaria y el calendario parecería completo sin serlo).
Resultados y dividendos de NASDAQ se cruzan solo con posiciones en bolsa US y
USD (misma regla que ``market_refresh_service._us_listed``): un ticker pelado
de un emisor no-US puede coincidir con otro emisor.

Honestidad de datos: solo se emiten eventos que la fuente trae; nada se
estima ni se inventa. Si NASDAQ no responde, el estado lo dice y las acciones
corporativas propias siguen apareciendo. ``source`` nombra el origen de cada
evento.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Company, CorporateAction, Position
from app.services.market_refresh_service import _us_listed

SOURCE_NASDAQ = "Calendario publico de NASDAQ"
SOURCE_CAVAAI = "Accion corporativa registrada en CavaAI"

_TYPE_ORDER = {"earnings": 0, "dividend_ex": 1, "corporate_action": 2}

# Valores reales de ``time`` del calendario NASDAQ (medidos), mas los alias antiguos.
_TIME_LABEL = {
    "time-pre-market": "antes de la apertura",
    "time-after-hours": "tras el cierre",
    "before-market": "antes de la apertura",
    "after-market": "tras el cierre",
}


def _es_number(value: float, decimals: int) -> str:
    """Numero con coma decimal y signo menos explicito (es-ES)."""
    return f"{value:.{decimals}f}".replace(".", ",")


def held_tickers(db: Session) -> tuple[set[str], set[str]]:
    """(todos, solo_us): tickers en mayusculas con posicion abierta.

    ``solo_us`` (bolsa US y USD) es el unico conjunto valido para cruzar con
    NASDAQ; ``todos`` sirve para las acciones corporativas propias."""
    companies = db.scalars(
        select(Company).join(Position, Position.company_id == Company.id).where(Position.quantity > 0)
    ).all()
    todos = {str(c.ticker).upper() for c in companies if c.ticker}
    solo_us = {str(c.ticker).upper() for c in companies if c.ticker and _us_listed(c)}
    return todos, solo_us


def _parse_us_date(value: Any) -> date | None:
    """NASDAQ entrega fechas como ``YYYY-MM-DD`` o ``MM/DD/YYYY``; otra cosa = None."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    try:
        if "/" in text:
            month, day, year = text.split("/")
            return date(int(year), int(month), int(day))
        return date.fromisoformat(text)
    except ValueError:
        return None


def build_catalysts(
    *,
    held: set[str],
    held_us: set[str],
    desde: date,
    hasta: date,
    earnings: list[dict[str, Any]],
    dividends: list[dict[str, Any]],
    actions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Filtra a cartera, normaliza y ordena por fecha. Funcion pura."""
    events: list[dict[str, Any]] = []
    for row in earnings:
        ticker = str(row.get("symbol", "")).upper()
        day = _parse_us_date(row.get("date"))
        if ticker not in held_us or day is None or not desde <= day <= hasta:
            continue
        detail = []
        # Solo franjas conocidas: "time-not-supplied" o valores nuevos no se muestran crudos.
        if row.get("time") in _TIME_LABEL:
            detail.append(_TIME_LABEL[row["time"]])
        if row.get("eps_forecast") is not None:
            detail.append(f"BPA estimado {_es_number(row['eps_forecast'], 2)}")
        events.append(
            {
                "date": day.isoformat(),
                "ticker": ticker,
                "type": "earnings",
                "title": "Resultados trimestrales",
                "detail": ", ".join(detail) or None,
                "source": SOURCE_NASDAQ,
            }
        )
    for row in dividends:
        ticker = str(row.get("symbol", "")).upper()
        if ticker not in held_us:
            continue
        amount = row.get("amount")
        amount_txt = (
            f"{_es_number(amount, 4)} por accion" if isinstance(amount, (int, float)) else None
        )
        day = _parse_us_date(row.get("ex_date"))
        if day is None or not desde <= day <= hasta:
            continue
        events.append(
            {
                "date": day.isoformat(),
                "ticker": ticker,
                "type": "dividend_ex",
                "title": "Fecha ex-dividendo",
                "detail": amount_txt,
                "source": SOURCE_NASDAQ,
            }
        )
    for action in actions:
        ticker = str(action.get("ticker", "")).upper()
        day = _parse_us_date(action.get("effective_date"))
        if ticker not in held or day is None or not desde <= day <= hasta:
            continue
        kind = str(action.get("action_type", ""))
        label = {
            "split": "Split",
            "reverse_split": "Contrasplit",
            "ticker_change": "Cambio de ticker",
            "merger": "Fusion",
            "spin_off": "Escision",
        }.get(kind, "Accion corporativa")
        ratio = action.get("ratio")
        events.append(
            {
                "date": day.isoformat(),
                "ticker": ticker,
                "type": "corporate_action",
                "title": label,
                "detail": f"ratio {_es_number(float(ratio), 4).rstrip('0').rstrip(',')}" if isinstance(ratio, (int, float)) else None,
                "source": SOURCE_CAVAAI,
            }
        )
    events.sort(key=lambda e: (e["date"], _TYPE_ORDER[e["type"]], e["ticker"]))
    return events


def pending_actions(db: Session, desde: date, hasta: date) -> list[dict[str, Any]]:
    """Acciones corporativas no aplicadas con fecha efectiva en el rango."""
    rows = db.execute(
        select(CorporateAction, Company.ticker)
        .join(Company, CorporateAction.company_id == Company.id)
        .where(
            CorporateAction.applied.is_(False),
            CorporateAction.effective_date >= desde,
            CorporateAction.effective_date <= hasta,
        )
    ).all()
    return [
        {
            "ticker": ticker,
            "action_type": action.action_type,
            "effective_date": action.effective_date.isoformat(),
            "ratio": float(action.ratio),
        }
        for action, ticker in rows
    ]


def combine_status(*statuses: str) -> str:
    """ok si todo ok; unavailable si ninguna fuente externa respondio; partial si mezcla."""
    if all(s == "ok" for s in statuses):
        return "ok"
    if all(s == "unavailable" for s in statuses):
        return "unavailable"
    return "partial"
