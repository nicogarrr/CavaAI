"""Read-only momentum from stored adjusted daily bars, never a fabricated return."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Company, MarketPrice


def load_momentum(db: Session, ticker: str, now: datetime) -> dict:
    day = (now.replace(tzinfo=UTC) if now.tzinfo is None else now.astimezone(UTC)).date()
    company = db.scalar(select(Company).where(Company.ticker == ticker))
    out: dict = {"calculado_en": now.isoformat(), "base": "retorno sobre cierre ajustado guardado; no es cotizacion en vivo", "ventanas": []}
    if company is None:
        return {**out, "aviso": "sin_empresa"}
    # Seed/spot rows do not establish adjusted market history. No network calls or writes.
    rows = db.execute(select(MarketPrice.date, MarketPrice.adj_close, MarketPrice.source).where(
        MarketPrice.company_id == company.id,
        MarketPrice.date <= day,
        MarketPrice.date >= day - timedelta(days=380),
        MarketPrice.source == "yfinance",
    ).order_by(MarketPrice.date)).all()
    bars = [(d, Decimal(str(p)), source) for d, p, source in rows if p is not None and Decimal(str(p)).is_finite() and p > 0]
    if not bars or (day - bars[-1][0]).days > 5:
        return {**out, "aviso": "sin_serie_ajustada_reciente"}
    end_day, end_price, source = bars[-1]
    for days in (30, 90, 180, 365):
        target = end_day - timedelta(days=days)
        past = [(d, p) for d, p, _ in bars if d <= target and (target - d).days <= 7]
        if not past:
            out["ventanas"].append({"dias": days, "retorno": None, "aviso": "sin_barra_inicial_cercana"})
            continue
        start_day, start_price = past[-1]
        out["ventanas"].append({"dias": days, "retorno": str((end_price - start_price) / start_price), "fecha_inicio": start_day.isoformat(), "fecha_fin": end_day.isoformat(), "fuente": source})
    return out
