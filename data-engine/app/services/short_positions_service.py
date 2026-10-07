"""Explicit on-demand refresh, persisted reads, no provider work in GET."""
from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta

import httpx
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import Company, ConnectorState
from app.services.cnmv_mapping import resolve_issuer
from app.services.connectors.cnmv_shorts import fetch_positions
from app.services.connectors.short_interest import fetch_short_volume
from app.services.data_health_service import utc

CONNECTOR = "public_shorts"


def _state(db: Session, company: Company) -> ConnectorState | None:
    tenant = db.info.get("tenant_id")
    if tenant is None:
        raise ValueError("Tenant context required")
    return db.scalar(select(ConnectorState).where(ConnectorState.tenant_id == tenant,
                     ConnectorState.company_id == company.id, ConnectorState.connector == CONNECTOR,
                     ConnectorState.feed_url == "public-shorts"))


def read_shorts(db: Session, company: Company) -> dict:
    state = _state(db, company)
    payload = state.metadata_ if state and isinstance(state.metadata_, dict) else {}
    stamp = utc(state.last_success_at) if state else None
    stale = bool(stamp and datetime.now(UTC) - stamp > timedelta(days=4))
    if payload.get("source") == "FINRA" and payload.get("date"):
        stale = stale or (datetime.now(UTC).date() - date.fromisoformat(payload["date"]) > timedelta(days=4))
    return {"ticker": company.ticker, "status": "degraded" if state and state.consecutive_errors else "stale" if stale else "available" if payload else "empty",
            "fetched_at": stamp.isoformat() if stamp else None, "data": payload or None,
            "reason": "No hay mapeo revisado para esta bolsa o empresa." if state and state.last_error == "UnsupportedMarket" else "La fuente no devolvió datos verificables; el dato anterior conserva su fecha." if state and state.consecutive_errors else "Consulta o fecha de negociación fuera del límite de 4 días." if stale else "No hay consulta almacenada. Usa Actualizar para consultar la fuente pública." if not payload else None}


async def refresh_shorts(db: Session, company: Company) -> dict:
    tenant = db.info.get("tenant_id")
    if tenant is None:
        raise ValueError("Tenant context required")
    if db.get_bind().dialect.name == "postgresql":
        key = int.from_bytes(hashlib.sha256(f"public-shorts:{tenant}:{company.id}".encode()).digest()[:8], "big", signed=True)
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
    state = _state(db, company)
    now = datetime.now(UTC)
    if state and state.last_started_at and now - utc(state.last_started_at) < timedelta(hours=1):
        return read_shorts(db, company)
    if state is None:
        state = ConnectorState(tenant_id=db.info["tenant_id"], company_id=company.id,
                               connector=CONNECTOR, feed_url="public-shorts")
        db.add(state)
    ticker, exchange = company.ticker, company.exchange.upper()
    issuer = resolve_issuer(ticker)
    state_id = state.id
    state.last_started_at = now
    db.commit()
    state_id = state_id or state.id
    # End any refresh SELECT transaction before awaiting a provider.
    db.commit()
    try:
        if issuer:
            payload = await fetch_positions(issuer)
        elif exchange in {"NASDAQ", "NYSE", "AMEX", "NYSEARCA", "NYSE ARCA", "US"} and "." not in ticker:
            async with httpx.AsyncClient(timeout=5) as client:
                row = await fetch_short_volume(ticker, client=client, lookback_days=4)
            if row is None:
                raise ValueError("No FINRA row")
            if date.fromisoformat(row["date"]) > now.date():
                raise ValueError("Future FINRA trade date")
            payload = {**row, "source": "FINRA", "kind": "OFICIAL", "ratio_kind": "DERIVADO",
                       "note": "Volumen corto diario fuera de bolsa, no posiciones abiertas ni porcentaje total del mercado. No implica sentimiento bajista por sí solo."}
        else:
            state.last_error = "UnsupportedMarket"
            state.consecutive_errors = (state.consecutive_errors or 0) + 1
            db.commit()
            return read_shorts(db, company)
        state = db.get(ConnectorState, state_id)
        state.metadata_ = payload
        state.last_success_at = now
        state.consecutive_errors = 0
        state.last_error = None
    except Exception as exc:  # noqa: BLE001 - never expose upstream strings/secrets
        state = db.get(ConnectorState, state_id)
        state.consecutive_errors = (state.consecutive_errors or 0) + 1
        state.last_error = type(exc).__name__
    db.commit()
    return read_shorts(db, company)
