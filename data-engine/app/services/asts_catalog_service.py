"""Tenant-scoped, persisted AST catalog. The GET path never contacts CelesTrak."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
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


def _acquire_catalog_lease(db: Session, tenant_id: int) -> None:
    # Serializa el get-or-create de ConnectorState: el unique admite company_id
    # NULL multiples veces en Postgres, asi que sin lease dos ejecuciones
    # concurrentes crearian duplicados y _state() fallaria despues.
    if db.get_bind().dialect.name != "postgresql":
        return
    key = int.from_bytes(
        hashlib.sha256(f"asts-catalog:{tenant_id}:{CONNECTOR}".encode()).digest()[:8],
        "big", signed=True)
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def persist_catalog(db: Session, catalog: list[dict], fetched_at: datetime) -> int:
    if not catalog or fetched_at.tzinfo is None:
        raise ValueError("Invalid AST catalog snapshot")
    tenant_id = db.info.get("tenant_id")
    if tenant_id is None:
        raise ValueError("Tenant context required for AST catalog")
    _acquire_catalog_lease(db, tenant_id)
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
        "freshness_basis": "download_time",
        "usage_note": (
            "Inventario observado: la frescura es la de la ultima descarga; el EPOCH "
            "orbital de cada objeto puede ser anterior al fetch. Apto como inventario, "
            "no para posiciones actuales, mapas ni trayectorias."),
        "source": "celestrak", "source_url": SOURCE_URL,
        "fetched_at": fetched_at.isoformat() if fetched_at else None,
        "satellites": satellites if fresh else [], "count": len(satellites) if fresh else 0,
        "stale_snapshot_at": fetched_at.isoformat() if fetched_at and not fresh else None,
    }
