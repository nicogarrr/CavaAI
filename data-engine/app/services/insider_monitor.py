"""PR-3: monitor programado de la watchlist/cartera contra SEC Form 4.

Escanea SOLO los emisores que el usuario sigue (watch_items + posiciones),
nunca el universo entero. Cada corrida:

- resuelve ticker -> CIK (Company.cik primero; company_tickers.json si falta);
- pide los Form 4 recientes de cada emisor (submissions API, gratis);
- salta los accessions ya persistidos (#82) y solo descarga/parsea los nuevos,
  con un presupuesto acotado de descargas por corrida y una pausa entre
  peticiones (muy por debajo del limite de 10 rps de la SEC);
- deja watermark + metricas en connector_states (connector="insider_monitor"):
  runs, filings nuevos, errores consecutivos, ultimo error.

Los schedulers (intervalo 15 min, catch-up diario, reconciliacion semanal)
solo varian `lookback` y `max_new_fetches`. Todo es best-effort por filing:
un XML roto no detiene la corrida; un fallo global incrementa
consecutive_errors y deja last_error, nunca lanza al caller del actor.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    Company,
    ConnectorState,
    InsiderFiling,
    Position,
    WatchItem,
)
from app.services import insider_persistence
from app.services.connectors import form4 as form4_connector
from app.services.insider_service import _cik_for_ticker

CONNECTOR_NAME = "insider_monitor"
DEFAULT_DELAY_SECONDS = 0.15


def _utcnow() -> datetime:
    return datetime.now(UTC)


def watchlist_tickers(db: Session, tenant_id: int | None = None) -> list[str]:
    """Simbolos seguidos: watchlist + companias con posicion en cartera."""
    symbols = {
        row.symbol.upper()
        for row in db.scalars(
            select(WatchItem).where(
                WatchItem.tenant_id.is_(tenant_id) if tenant_id is None
                else WatchItem.tenant_id == tenant_id
            )
        )
        if row.symbol
    }
    company_ids = db.scalars(
        select(Position.company_id).where(
            Position.tenant_id.is_(tenant_id) if tenant_id is None
            else Position.tenant_id == tenant_id
        )
    ).all()
    if company_ids:
        symbols |= {
            c.ticker.upper()
            for c in db.scalars(select(Company).where(Company.id.in_(company_ids)))
            if c.ticker
        }
    return sorted(symbols)


def resolve_ciks(
    db: Session,
    tickers: list[str],
    *,
    client=None,
) -> dict[str, str]:
    """ticker -> CIK, usando Company.cik y rellenando desde la SEC."""
    resolved: dict[str, str] = {}
    for ticker in tickers:
        company = db.scalar(select(Company).where(Company.ticker == ticker))
        cik = (company.cik or "").strip() if company else ""
        if not cik:
            cik = _cik_for_ticker(ticker, client) or ""
            if cik and company is not None:
                company.cik = cik
                db.add(company)
                db.commit()
        if cik:
            resolved[ticker] = cik
    return resolved


def _connector_state(db: Session, tenant_id: int | None) -> ConnectorState:
    state = db.scalar(
        select(ConnectorState).where(
            ConnectorState.connector == CONNECTOR_NAME,
            ConnectorState.tenant_id.is_(tenant_id) if tenant_id is None
            else ConnectorState.tenant_id == tenant_id,
            ConnectorState.company_id.is_(None),
        )
    )
    if state is None:
        state = ConnectorState(tenant_id=tenant_id, connector=CONNECTOR_NAME)
        db.add(state)
        db.flush()
    return state


def scan(
    db: Session,
    *,
    tenant_id: int | None = None,
    lookback: int = 20,
    max_new_fetches: int = 25,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    sleeper: Callable[[float], None] = time.sleep,
    client=None,
    fetcher: Callable[[dict], str] | None = None,
) -> dict[str, Any]:
    """Una corrida acotada del monitor. Devuelve stats; nunca lanza."""
    state = _connector_state(db, tenant_id)
    state.last_started_at = _utcnow()
    db.add(state)
    db.commit()

    stats: dict[str, Any] = {
        "connector": CONNECTOR_NAME,
        "lookback": lookback,
        "tickers_scanned": 0,
        "filings_seen": 0,
        "filings_new": 0,
        "transactions_created": 0,
        "errors": [],
        "status": "ok",
    }
    try:
        tickers = watchlist_tickers(db, tenant_id)
        if not tickers:
            stats["status"] = "skipped"
            stats["reason"] = "watchlist and portfolio are empty"
            _record_success(db, state, stats)
            return stats
        ciks = resolve_ciks(db, tickers, client=client)
        missing = [t for t in tickers if t not in ciks]
        if missing:
            stats["errors"].append(f"sin CIK SEC: {', '.join(missing)}")

        # Filtro por tenant explicito. Sin el, el set traia los accessions de
        # TODOS los tenants: el tenant B veia el accession que el tenant A ya
        # habia persistido y lo saltaba, asi que nunca recibia esos Form 4.
        # Un select() de una sola columna no dispara el with_loader_criteria
        # que inyecta database.py (los loader criteria aplican a la carga de
        # entidades, no a tuplas de columnas).
        known_accessions = {
            row[0]
            for row in db.execute(
                select(InsiderFiling.accession_number).where(
                    InsiderFiling.tenant_id == db.info.get("tenant_id")
                )
            ).all()
        }
        budget = max_new_fetches
        for ticker, cik in ciks.items():
            if budget <= 0:
                stats["errors"].append("presupuesto de descargas agotado")
                break
            stats["tickers_scanned"] += 1
            filings = form4_connector.recent_form4_filings(cik, limit=lookback, client=client)
            stats["filings_seen"] += len(filings)
            for filing in filings:
                accession = str(filing.get("accession_number") or "")
                if not accession or accession in known_accessions:
                    continue
                if budget <= 0:
                    break
                budget -= 1
                try:
                    if fetcher is not None:
                        xml_text = fetcher(filing)
                    else:
                        xml_text = form4_connector.fetch_filing_xml(
                            filing["document_url"], client=client
                        )
                    parsed = form4_connector.parse_form4_xml(xml_text)
                    persisted = insider_persistence.persist_filing(
                        db, filing, parsed, xml_text=xml_text, tenant_id=tenant_id
                    )
                    known_accessions.add(accession)
                    stats["filings_new"] += 1 if persisted["filing_created"] else 0
                    stats["transactions_created"] += persisted["transactions_created"]
                except Exception as exc:  # noqa: BLE001 - best-effort por filing
                    stats["errors"].append(f"{accession}: {type(exc).__name__}")
                if delay_seconds > 0:
                    sleeper(delay_seconds)

        if stats["errors"]:
            stats["status"] = "partial" if stats["tickers_scanned"] else "error"
        _record_success(db, state, stats)
        return stats
    except Exception as exc:  # noqa: BLE001 - el actor jamas recibe una excepcion
        stats["status"] = "error"
        stats["errors"].append(f"fatal: {type(exc).__name__}: {exc}")
        state.consecutive_errors = (state.consecutive_errors or 0) + 1
        state.last_error = f"{type(exc).__name__}: {exc}"[:1000]
        meta = dict(state.metadata_ or {})
        meta["runs"] = int(meta.get("runs", 0)) + 1
        meta["last_run"] = stats
        state.metadata_ = meta
        db.add(state)
        db.commit()
        return stats


def _record_success(db: Session, state: ConnectorState, stats: dict[str, Any]) -> None:
    state.last_success_at = _utcnow()
    state.consecutive_errors = 0
    state.last_error = None
    state.cursor = stats.get("status")
    meta = dict(state.metadata_ or {})
    meta["runs"] = int(meta.get("runs", 0)) + 1
    meta["filings_new_total"] = int(meta.get("filings_new_total", 0)) + stats["filings_new"]
    meta["transactions_total"] = (
        int(meta.get("transactions_total", 0)) + stats["transactions_created"]
    )
    meta["last_run"] = stats
    state.metadata_ = meta
    db.add(state)
    db.commit()
