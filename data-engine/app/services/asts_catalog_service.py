"""Tenant-scoped, persisted AST catalog. The GET path never contacts CelesTrak."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import ConnectorState
from app.services.asts_orbit_service import append_history, orbit_signal
from app.services.connectors.celestrak_ast import SOURCE_URL
from app.services.connectors.celestrak_ast_supgp import SUPGP_URL

CONNECTOR = "celestrak_ast"
FRESH_FOR = timedelta(hours=30)
MIN_FETCH_INTERVAL = timedelta(hours=2)


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


def latest_download_at(db: Session) -> datetime | None:
    """Guard the shared fetch before contacting either CelesTrak endpoint."""
    state = _state(db)
    if state is None:
        return None
    stamps = (state.last_started_at, state.last_success_at)
    return max((stamp for stamp in stamps if stamp is not None), default=None)


def record_download_attempt(db: Session, fetched_at: datetime) -> None:
    """Persist attempted fetch even when either endpoint fails (rate-limit safety)."""
    tenant_id = db.info.get("tenant_id")
    if tenant_id is None:
        raise ValueError("Tenant context required for AST catalog")
    _acquire_catalog_lease(db, tenant_id)
    state = _state(db)
    if state is None:
        state = ConnectorState(tenant_id=tenant_id, connector=CONNECTOR,
                               feed_url=SOURCE_URL, company_id=None)
        db.add(state)
    state.last_started_at = fetched_at
    db.commit()


def persist_catalog(db: Session, catalog: list[dict], fetched_at: datetime,
                    *, supgp: list[dict] | None = None) -> int:
    if (not catalog and supgp is None) or fetched_at.tzinfo is None:
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
    previous = state.metadata_ if isinstance(state.metadata_, dict) else {}
    history = append_history(previous.get("orbit_history"), catalog)
    metadata = dict(previous)
    if catalog:
        metadata.update({"satellites": catalog, "orbit_history": history,
                         "source": "celestrak", "source_url": SOURCE_URL,
                         "fetched_at": fetched_at.astimezone(UTC).isoformat()})
    if supgp is not None:
        metadata.update({"supgp_satellites": supgp,
                         "supgp_history": append_history(previous.get("supgp_history"), supgp),
                         "supgp_fetched_at": fetched_at.astimezone(UTC).isoformat(),
                         "supgp_source_url": SUPGP_URL})
    else:
        # Independent failure: do not claim new SupGP data, but preserve the
        # prior source until its own 30h freshness expires.
        metadata.update({key: previous[key] for key in (
            "supgp_satellites", "supgp_history", "supgp_fetched_at", "supgp_source_url"
        ) if key in previous})
    state.metadata_ = metadata
    # last_started_at tracks outbound attempts, not successful persistence.
    # Keeping the original attempt time prevents a late tenant copy from
    # extending the global 2h guard or making stale GP look freshly fetched.
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


def read_orbit_history(db: Session, norad_cat_id: int, *, as_of: datetime | None = None) -> dict:
    """Read only; stale catalog fails closed even if old history remains stored."""
    catalog = read_catalog(db, as_of=as_of)
    base = {"norad_cat_id": norad_cat_id, "source": "CelesTrak", "source_url": SOURCE_URL,
            "cadence_hours": 2, "fetched_at": catalog["fetched_at"],
            "status": "sin datos", "history": [], "signal": None,
            "usage_note": "Señal exploratoria calculada sobre elementos orbitales. BSTAR y derivadas son parámetros de ajuste, no telemetría ni confirmación de despliegue."}
    satellite = next((item for item in catalog["satellites"] if item["norad_cat_id"] == norad_cat_id), None)
    if satellite is None:
        return base
    state = _state(db)
    history = (state.metadata_ or {}).get("orbit_history", {}).get(str(norad_cat_id), []) if state else []
    if not isinstance(history, list):
        history = []
    return {**base, "status": "disponible", "object_name": satellite["object_name"],
            "epoch": satellite["epoch"], "history": history, "signal": orbit_signal(history, as_of=as_of)}


def read_orbit_overview(db: Session, *, as_of: datetime | None = None) -> dict:
    catalog = read_catalog(db, as_of=as_of)
    base = {"status": catalog["status"], "source": "CelesTrak", "source_url": SOURCE_URL,
            "cadence_hours": 2, "fetched_at": catalog["fetched_at"], "objects": [],
            "usage_note": "Señal exploratoria calculada sobre elementos orbitales. BSTAR y derivadas son parámetros de ajuste, no telemetría ni confirmación de despliegue."}
    state = _state(db)
    history = (state.metadata_ or {}).get("orbit_history", {}) if state else {}
    objects = []
    for item in catalog["satellites"]:
        samples = history.get(str(item["norad_cat_id"]), []) if isinstance(history, dict) else []
        if not isinstance(samples, list):
            samples = []
        objects.append({"norad_cat_id": item["norad_cat_id"], "object_name": item["object_name"],
                        "epoch": item["epoch"], "sma_km": samples[-1]["sma_km"] if samples else None,
                        "signal": orbit_signal(samples, as_of=as_of), "history": samples})
    supgp_fetched = (state.metadata_ or {}).get("supgp_fetched_at") if state else None
    now = as_of or datetime.now(UTC)
    try:
        supgp_at = datetime.fromisoformat(supgp_fetched) if supgp_fetched else None
        supgp_fresh = bool(supgp_at and supgp_at.tzinfo and supgp_at <= now
                            and now - supgp_at <= FRESH_FOR)
    except (TypeError, ValueError):
        supgp_fresh = False
    supgp_items = (state.metadata_ or {}).get("supgp_satellites", []) if state and supgp_fresh else []
    supgp_hist = (state.metadata_ or {}).get("supgp_history", {}) if state and supgp_fresh else {}
    supplemental = []
    for item in supgp_items if isinstance(supgp_items, list) else []:
        samples = supgp_hist.get(str(item["norad_cat_id"]), []) if isinstance(supgp_hist, dict) else []
        if not isinstance(samples, list):
            samples = []
        supplemental.append({"norad_cat_id": item["norad_cat_id"], "object_name": item["object_name"],
                             "epoch": item["epoch"], "sma_km": samples[-1]["sma_km"] if samples else None,
                             "signal": orbit_signal(samples, as_of=as_of), "history": samples})
    return {**base, "objects": objects, "supgp": {
        "status": "disponible" if supgp_fresh and supplemental else "sin datos",
        "source": "CelesTrak SupGP (AST-E)", "source_url": SUPGP_URL,
        "fetched_at": supgp_fetched if supgp_fresh else None,
        "objects": supplemental if supgp_fresh else [],
    }}
