"""Tenant-scoped, persisted AST catalog. The GET path never contacts CelesTrak."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ConnectorState
from app.services.connectors.celestrak_ast import SOURCE_URL

CONNECTOR = "celestrak_ast"
FRESH_FOR = timedelta(hours=30)


def _state(db: Session) -> ConnectorState | None:
    tenant_id = db.info.get("tenant_id")
    if tenant_id is None:
        raise ValueError("Tenant context required for AST catalog")
    return db.scalar(select(ConnectorState).where(
        ConnectorState.tenant_id == tenant_id,
        ConnectorState.connector == CONNECTOR,
        ConnectorState.company_id.is_(None),
        ConnectorState.feed_url == SOURCE_URL,
    ))


def persist_catalog(db: Session, catalog: list[dict], fetched_at: datetime) -> int:
    if not catalog or fetched_at.tzinfo is None:
        raise ValueError("Invalid AST catalog snapshot")
    state = _state(db)
    if state is None:
        state = ConnectorState(
            tenant_id=db.info["tenant_id"], connector=CONNECTOR,
            feed_url=SOURCE_URL, company_id=None,
        )
        db.add(state)
    state.metadata_ = {"satellites": catalog, "source": "celestrak", "source_url": SOURCE_URL,
                       "fetched_at": fetched_at.astimezone(UTC).isoformat()}
    state.last_started_at = fetched_at
    state.last_success_at = fetched_at
    state.consecutive_errors = 0
    state.last_error = None
    db.commit()
    return len(catalog)


def read_catalog(db: Session, *, as_of: datetime | None = None) -> dict:
    now = as_of or datetime.now(UTC)
    state = _state(db)
    metadata = (state.metadata_ or {}) if state else {}
    fetched = metadata.get("fetched_at")
    try:
        fetched_at = datetime.fromisoformat(fetched) if fetched else None
        if fetched_at and fetched_at.tzinfo is None:
            fetched_at = None
    except (TypeError, ValueError):
        fetched_at = None
    satellites = metadata.get("satellites") if isinstance(metadata.get("satellites"), list) else []
    fresh = bool(fetched_at and fetched_at <= now and now - fetched_at <= FRESH_FOR and satellites)
    return {
        "ticker": "ASTS", "status": "disponible" if fresh else "sin datos",
        "source": "celestrak", "source_url": SOURCE_URL,
        "fetched_at": fetched_at.isoformat() if fetched_at else None,
        "satellites": satellites if fresh else [], "count": len(satellites) if fresh else 0,
        "stale_snapshot_at": fetched_at.isoformat() if fetched_at and not fresh else None,
    }
