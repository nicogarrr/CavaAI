"""Dated, tenant-scoped digest of held symbols. Related news is not causal proof."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import Company, MarketPrice, NewsEvent, PortfolioMoveDigest, Position

VERSION = "held-price-moves-v1"


def build_digest(db: Session, as_of: date, generated_at: datetime | None = None) -> PortfolioMoveDigest:
    if db.info.get("tenant_id") is None:
        raise ValueError("Tenant context required")
    generated_at = generated_at or datetime.now(UTC)
    # An as-of day that has not finished in UTC cannot be called a completed close.
    if generated_at.tzinfo is None or as_of >= generated_at.astimezone(UTC).date():
        raise ValueError("Only prior completed UTC dates may be summarized")
    positions = db.scalars(select(Position).where(Position.quantity > 0).order_by(Position.id)).all()
    items = []
    for position in positions:
        company = db.get(Company, position.company_id)
        if not company:
            continue
        prices = db.scalars(select(MarketPrice).where(
            MarketPrice.company_id == company.id,
            MarketPrice.date <= as_of,
            MarketPrice.date >= as_of - timedelta(days=8),
        ).order_by(desc(MarketPrice.date)).limit(2)).all()
        current = prices[0] if prices and prices[0].date == as_of and prices[0].close and prices[0].close > 0 else None
        prior = prices[1] if current and len(prices) > 1 and prices[1].close and prices[1].close > 0 else None
        item = {"position_id": position.id, "company_id": company.id, "ticker": company.ticker,
                "quantity": str(position.quantity), "date": as_of.isoformat(), "status": "sin datos",
                "catalyst": "sin catalizador identificado", "related_news": []}
        if current and prior:
            change_pct = (Decimal(current.close) / Decimal(prior.close) - 1) * 100
            item.update(status="disponible", close=str(current.close), previous_close=str(prior.close),
                        previous_date=prior.date.isoformat(), price_change_pct=round(float(change_pct), 4),
                        price_source=current.source, previous_price_source=prior.source,
                        price_ids=[prior.id, current.id])
            # GDELT ingestion stores the actual article domain as NewsEvent.source.
            # Its connector identity is not persisted, so label these only as
            # dated, sourced related articles, not verified GDELT or catalysts.
            start = datetime.combine(as_of, time.min, tzinfo=UTC)
            end = start + timedelta(days=1)
            news = db.scalars(select(NewsEvent).where(
                NewsEvent.company_id == company.id, NewsEvent.date >= start, NewsEvent.date < end,
                NewsEvent.url.is_not(None),
            ).order_by(desc(NewsEvent.date)).limit(5)).all()
            item["related_news"] = [{"id": row.id, "title": row.title, "url": row.url,
                                    "source": row.source, "published_at": row.date.isoformat()}
                                   for row in news]
        else:
            item["missing"] = ["cierre fechado" if not current else "cierre anterior"]
        items.append(item)
    coverage = "sin posiciones" if not items else "completa" if all(item["status"] == "disponible" for item in items) else "parcial"
    checksum = hashlib.sha256(json.dumps(items, sort_keys=True).encode()).hexdigest()
    previous = db.scalar(select(PortfolioMoveDigest).where(
        PortfolioMoveDigest.tenant_id == db.info["tenant_id"],
        PortfolioMoveDigest.digest_date == as_of, PortfolioMoveDigest.version == VERSION,
        PortfolioMoveDigest.input_hash == checksum,
    ))
    if previous:
        return previous
    digest = PortfolioMoveDigest(tenant_id=db.info["tenant_id"], digest_date=as_of,
                                 version=VERSION, input_hash=checksum, items=items,
                                 coverage=coverage, generated_at=generated_at)
    db.add(digest)
    db.commit()
    db.refresh(digest)
    return digest


def latest_digest(db: Session) -> dict:
    if db.info.get("tenant_id") is None:
        raise ValueError("Tenant context required")
    digest = db.scalar(select(PortfolioMoveDigest).where(
        PortfolioMoveDigest.tenant_id == db.info["tenant_id"],
    ).order_by(desc(PortfolioMoveDigest.digest_date), desc(PortfolioMoveDigest.id)).limit(1))
    if digest is None:
        return {"status": "sin datos", "items": [], "coverage": "sin datos"}
    age = (datetime.now(UTC).date() - digest.digest_date).days
    return {"status": "obsoleto" if age > 4 else "disponible", "date": digest.digest_date.isoformat(),
            "generated_at": digest.generated_at.isoformat(), "version": digest.version,
            "coverage": digest.coverage, "items": digest.items,
            "note": "Noticias relacionadas por fecha, no atribución causal; sin catalizador identificado."}
