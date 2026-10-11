"""Resumen diario "que paso con lo mio" como ResearchAlert enrutable.

El digest lo construye build_digest; este emisor lo resume en texto de
plantilla (sin LLM): cada variacion va con fuente (cierres ajustados de
yfinance) y fecha explicitas, y lo no cubierto se nombra como "sin datos",
nunca como 0.
"""
from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import PortfolioMoveDigest, ResearchAlert

VERSION = "daily-digest-alert-v1"

_MAX_LINEAS = 16


def _fingerprint(tenant_id: int, as_of: date) -> str:
    raw = f"{VERSION}:{tenant_id}:{as_of.isoformat()}".encode()
    return hashlib.sha256(raw).hexdigest()


def _fmt_pct(value: object) -> str | None:
    try:
        return f"{float(value):+.2f}%"
    except (TypeError, ValueError):
        return None


def emit_digest_alert(db: Session, digest: PortfolioMoveDigest, as_of: date) -> ResearchAlert | None:
    """Persist the daily-digest alert once per tenant/day; None if already emitted.

    Privacy boundary: the digest must belong to the session tenant and match
    the requested as_of date; a foreign or stale digest is never announced.
    """
    tenant_id = db.info.get("tenant_id")
    if tenant_id is None:
        raise ValueError("Tenant context required")
    if digest.tenant_id != tenant_id:
        raise ValueError("Digest tenant does not match the session tenant")
    if digest.digest_date != as_of:
        raise ValueError("Digest date does not match the requested as_of")
    fp = _fingerprint(tenant_id, as_of)
    existing = db.scalar(select(ResearchAlert).where(
        ResearchAlert.tenant_id == tenant_id, ResearchAlert.fingerprint == fp,
    ))
    if existing is not None:
        return None
    items = digest.items or []
    disponibles = [i for i in items if i.get("status") == "disponible"]
    sin_datos = sorted({i.get("ticker") for i in items
                        if i.get("status") != "disponible" and i.get("ticker")})
    con_var = []
    for item in disponibles:
        pct = _fmt_pct(item.get("price_change_pct"))
        if item.get("ticker") and pct is not None:
            con_var.append((abs(float(item["price_change_pct"])), f"{item['ticker']} {pct}"))
    con_var.sort(reverse=True)
    lineas = [txt for _, txt in con_var[:_MAX_LINEAS]]
    if not items:
        resumen = "No habia posiciones abiertas que resumir."
    elif not disponibles:
        resumen = (f"{len(items)} posiciones seguidas, sin datos de cierre para el "
                   f"{as_of.isoformat()} (sin datos, no 0).")
    else:
        resumen = ", ".join(lineas) + "."
        if sin_datos:
            resumen += f" Sin datos: {', '.join(sin_datos)}."
    sampled = digest.generated_at
    if sampled.tzinfo is None:
        sampled = sampled.replace(tzinfo=UTC)
    sampled_txt = sampled.strftime("%Y-%m-%d %H:%M UTC")
    alert = ResearchAlert(
        tenant_id=tenant_id, company_id=None, severity="low", status="open",
        alert_type="daily_digest",
        title=f"Resumen diario de tu cartera al {as_of.isoformat()}",
        message=(resumen + " Variaciones del valor con cierres ajustados de yfinance al "
                 f"{as_of.isoformat()}, no el P&L de tu posicion. "
                 f"Cartera medida al generar el resumen ({sampled_txt}); "
                 "movimientos posteriores no estan incluidos. "
                 f"Cobertura del digest: {digest.coverage}."),
        fingerprint=fp, channels=["in_app"], last_triggered_at=datetime.now(UTC),
        metadata_={"digest_id": digest.id, "digest_date": as_of.isoformat(),
                   "coverage": digest.coverage, "rule_version": VERSION,
                   "price_source": "yfinance", "as_of": as_of.isoformat(),
                   "positions_sampled_at": sampled.isoformat()},
    )
    try:
        with db.begin_nested():
            db.add(alert)
            db.flush()
    except IntegrityError:
        return None
    db.commit()
    return alert
