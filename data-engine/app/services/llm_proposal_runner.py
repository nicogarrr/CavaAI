"""Cableado del motor de propuestas LLM (item 1): contexto real, cuota y presupuesto.

El modelo solo ve titulares ya guardados para la empresa y una cotizacion fresca.
Sin empresa seguida, sin titulares recientes, sin cotizacion, sin presupuesto o
con la cuota diaria agotada no se llama al modelo o no se guarda nada.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import threading
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.llm import create_llm_provider
from app.llm.model_aliases import VERIFIED_FREE_MODELS
from app.models.entities import Company, NewsEvent
from app.models.paper_trading import PaperTrade
from app.schemas.paper_trading import PaperProposal
from app.services.bottleneck_discovery_service import paid_model_risk
from app.services.budget import BudgetController, BudgetExceededError
from app.services.llm_proposal_service import PROPOSAL_TASK, ProposalRejected, propose
from app.services.llm_router import route_model
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


_quota_guard = threading.Lock()
_quota_locks: dict[tuple, threading.Lock] = {}


def _quota_lock(db: Session, now: datetime) -> threading.Lock:
    key = (db.info.get("tenant_id"), _utc(now).date())
    with _quota_guard:
        return _quota_locks.setdefault(key, threading.Lock())


def save_within_quota(db: Session, proposal: PaperProposal, now: datetime) -> PaperTrade:
    """Cuenta y guarda en una transaccion corta serializada por tenant y dia.

    Candado de proceso mas pg_advisory_xact_lock (varios workers). Se toma DESPUES
    del LLM y se suelta con el commit de create_proposal: nunca cubre cotizacion ni modelo.
    """
    db.commit()  # sin instantanea vieja: el count ve lo ya confirmado
    with _quota_lock(db, now):
        if db.get_bind().dialect.name == "postgresql":
            raw = f"llm-quota:{db.info.get('tenant_id')}:{_utc(now).date()}".encode()
            key = int.from_bytes(hashlib.sha256(raw).digest()[:8], "big") >> 1
            db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})
        if todays_llm_proposals(db, now) >= DAILY_QUOTA:
            db.rollback()
            raise QuotaExceeded(DAILY_QUOTA)
        try:
            return create_proposal(db, proposal)
        except Exception:
            db.rollback()
            raise


def load_headlines(db: Session, ticker: str, now: datetime) -> list[dict]:
    company = db.scalar(select(Company).where(Company.ticker == ticker))
    if company is None:
        raise ProposalRejected("empresa_no_seguida")
    rows = db.scalars(
        select(NewsEvent)
        .where(NewsEvent.company_id == company.id,
            NewsEvent.date >= _utc(now) - NEWS_WINDOW,
            NewsEvent.date <= _utc(now),  # sin evidencia con fecha futura
        )
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
    # Solo modelos gratuitos (EUR 0): se resuelve el modelo REAL (con overrides de
    # entorno) y el fallback del adaptador ANTES de gastar nada. Fail-closed.
    route = route_model(PROPOSAL_TASK)
    if route.model not in VERIFIED_FREE_MODELS:
        raise ProposalRejected("modelo_no_gratuito")
    blocked = paid_model_risk(provider, route.model, PROPOSAL_TASK)
    if blocked:
        raise ProposalRejected(blocked)
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
        try:
            allowed = budget.can_spend(db, 0.02)
        finally:
            db.commit()  # el SELECT del tope abre transaccion: se libera antes del 2o LLM
        if not allowed:
            raise BudgetExceededError("LLM budget exhausted")

    try:
        proposal = await propose(
            provider, ticker, quote=quote, headlines=headlines, now=now,
            on_response=_record, before_retry=_can_retry,
        )
    except BudgetExceededError as exc:
        raise ProposalRejected("presupuesto_agotado") from exc
    return save_within_quota(db, proposal, now)
