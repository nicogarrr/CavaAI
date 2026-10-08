"""Cableado del motor de propuestas LLM (item 1): contexto real, cuota y presupuesto.

El modelo solo ve titulares ya guardados para la empresa y una cotizacion fresca.
Sin empresa seguida, sin titulares recientes, sin cotizacion, sin presupuesto o
con la cuota diaria agotada no se llama al modelo o no se guarda nada.
"""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.llm import create_llm_provider
from app.models.entities import Company, NewsEvent
from app.models.paper_trading import PaperTrade
from app.services.budget import BudgetController
from app.services.llm_proposal_service import ProposalRejected, propose
from app.services.paper_trading_service import create_proposal

DAILY_QUOTA = 5  # propuestas LLM guardadas por tenant y dia UTC
NEWS_WINDOW = timedelta(days=14)
MAX_HEADLINES = 8
_TICKER = re.compile(r"^[A-Za-z0-9.^=-]{1,20}$")


class QuotaExceeded(Exception):
    def __init__(self, limit: int) -> None:
        super().__init__(f"cuota diaria de {limit} propuestas LLM agotada")
        self.limit = limit


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def todays_llm_proposals(db: Session, now: datetime) -> int:
    start = _utc(now).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(
        db.scalar(
            select(func.count(PaperTrade.id)).where(
                PaperTrade.proposal_key.like("llm:%"), PaperTrade.created_at >= start
            )
        )
        or 0
    )


def load_headlines(db: Session, ticker: str, now: datetime) -> list[dict]:
    company = db.scalar(select(Company).where(Company.ticker == ticker))
    if company is None:
        raise ProposalRejected("empresa_no_seguida")
    rows = db.scalars(
        select(NewsEvent)
        .where(NewsEvent.company_id == company.id, NewsEvent.date >= _utc(now) - NEWS_WINDOW)
        .order_by(NewsEvent.date.desc(), NewsEvent.id.desc())
        .limit(MAX_HEADLINES)
    ).all()
    # Copia escalares: la sesion se libera antes de cualquier E/S de red.
    return [
        {"id": f"news:{n.id}", "title": n.title, "published_at": _utc(n.date).isoformat(), "source": n.source}
        for n in rows
    ]


async def generate_proposal(
    db: Session,
    ticker: str,
    *,
    provider=None,
    fetch_quote=None,
    now: datetime | None = None,
) -> PaperTrade:
    now = now or datetime.now(UTC)
    ticker = (ticker or "").strip().upper()
    if not _TICKER.match(ticker):
        raise ProposalRejected("ticker_invalido")
    provider = provider or create_llm_provider()
    if provider.name == "disabled":
        raise ProposalRejected("llm_deshabilitado")
    budget = BudgetController()
    if not budget.can_spend(db, 0.02):
        raise ProposalRejected("presupuesto_agotado")
    if todays_llm_proposals(db, now) >= DAILY_QUOTA:
        raise QuotaExceeded(DAILY_QUOTA)
    headlines = load_headlines(db, ticker, now)
    if not headlines:
        raise ProposalRejected("sin_titulares")
    db.commit()  # sin conexion ni transaccion abiertas durante cotizacion y LLM
    if fetch_quote is None:
        from app.api.routes.market import market_quote as fetch_quote
    try:
        quote = await asyncio.to_thread(fetch_quote, ticker)
    except Exception:  # noqa: BLE001 - sin cotizacion no hay propuesta
        quote = None

    def _record(resp) -> None:
        # Cada respuesta del proveedor, tambien la que el validador descarta, consume presupuesto.
        cost = budget.estimate_cost_eur(resp.model, resp.usage.input_tokens, resp.usage.output_tokens)
        budget.record(db, resp.model, "llm_proposal", cost, resp.usage.total_tokens)

    def _can_retry() -> None:
        if not budget.can_spend(db, 0.02):
            raise RuntimeError("LLM budget exhausted")

    proposal = await propose(
        provider, ticker, quote=quote, headlines=headlines, now=now,
        on_response=_record, before_retry=_can_retry,
    )
    if todays_llm_proposals(db, now) >= DAILY_QUOTA:  # revalida tras la espera del modelo
        raise QuotaExceeded(DAILY_QUOTA)
    return create_proposal(db, proposal)
