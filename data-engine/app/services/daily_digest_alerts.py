
"""Resumen diario "que paso con lo mio" como ResearchAlert enrutable.

El digest lo construye build_digest (cifras con fuente y fecha propias); este
emisor solo lo anuncia. Texto de plantilla, sin LLM: las unicas cifras van con
fuente (yfinance, cierres ajustados) y fecha explicitas.
"""
from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import PortfolioMoveDigest, ResearchAlert

VERSION = "daily-digest-alert-v1"


def _fingerprint(tenant_id: int, as_of: date) -> str:
    raw = f"{VERSION}:{tenant_id}:{as_of.isoformat()}".encode()
    return hashlib.sha256(raw).hexdigest()


def emit_digest_alert(db: Session, digest: PortfolioMoveDigest, as_of: date) -> ResearchAlert | None:
    """Persist the daily-digest alert once per tenant/day; None if already emitted."""
    tenant_id = db.info.get("tenant_id")
    if tenant_id is None:
        raise ValueError("Tenant context required")
    fp = _fingerprint(tenant_id, as_of)
    existing = db.scalar(select(ResearchAlert).where(
        ResearchAlert.tenant_id == tenant_id, ResearchAlert.fingerprint == fp,
    ))
    if existing is not None:
        return None
    items = digest.items or []
    disponibles = [i for i in items if i.get("status") == "disponible"]
    tickers = sorted({i.get("ticker") for i in disponibles if i.get("ticker")})
    if not items:
        resumen = "No habia posiciones abiertas que resumir."
    elif not disponibles:
        resumen = (f"{len(items)} posiciones seguidas, sin datos de cierre para el "
                   f"{as_of.isoformat()} (sin datos, no 0).")
    else:
        resumen = (f"{len(disponibles)} de {len(items)} posiciones con cierre ajustado de "
                   f"yfinance al {as_of.isoformat()}: {", ".join(tickers)}.")
    alert = ResearchAlert(
        tenant_id=tenant_id, company_id=None, severity="low", status="open",
        alert_type="daily_digest",
        title=f"Resumen diario de tu cartera al {as_of.isoformat()}",
        message=(resumen + " Las variaciones son del valor con cierres ajustados de yfinance "
                 "a esa fecha, no el P&L de tu posicion. Cobertura del digest: "
                 f"{digest.coverage}. Detalle completo en la app."),
        fingerprint=fp, channels=["in_app"], last_triggered_at=datetime.now(UTC),
        metadata_={"digest_id": digest.id, "digest_date": as_of.isoformat(),
                   "coverage": digest.coverage, "rule_version": VERSION,
                   "price_source": "yfinance", "as_of": as_of.isoformat()},
    )
    try:
        with db.begin_nested():
            db.add(alert)
            db.flush()
    except IntegrityError:
        return None
    db.commit()
    return alert