"""F2: ingesta diaria de precios para el top-N de ProPicks + metricas de momentum.

Fuente: Yahoo Finance via yfinance (gratis, sin key). Tickers EUR (BME) usan el
sufijo .MC; el resto va tal cual (universo actual: US + BME).

Momentum: rentabilidad total 6m (126 dias) y 12m (252 dias) sobre adj_close,
persistida en calculated_metrics (momentum_6m / momentum_12m, period=fecha as_of)
para que el embudo pueda ponderarla despues. Sin imputacion: si no hay serie
suficiente no se escribe metrica.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Callable, Iterable, Mapping, Sequence

from sqlalchemy import desc, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import CalculatedMetric, Company, MarketPrice, ProPickCandidate, ProPickRun

MOMENTUM_WINDOWS: dict[str, int] = {"momentum_6m": 126, "momentum_12m": 252}
MIN_BARS_6M = 60   # ventanas minimas honestas (~3 meses de barras)
MIN_BARS_12M = 200
METRIC_VERSION = "v1"


def yahoo_symbol(company: Company) -> str:
    """Ticker Yahoo: BME cotiza con sufijo .MC; el resto va en crudo."""
    ticker = (company.ticker or "").strip()
    if (company.currency or "").upper() == "EUR" and "." not in ticker:
        return f"{ticker}.MC"
    return ticker


@dataclass(frozen=True)
class PriceBar:
    day: date
    close: Decimal
    adj_close: Decimal
    volume: int


def fetch_history_yfinance(
    symbols: Sequence[str], *, period: str = "1y"
) -> dict[str, list[PriceBar]]:
    """Descarga OHLCV diaria via yfinance. Aislado para poder inyectarlo en tests."""
    import yfinance as yf

    out: dict[str, list[PriceBar]] = {}
    for symbol in symbols:
        try:
            hist = yf.Ticker(symbol).history(period=period, auto_adjust=False)
        except Exception:
            out[symbol] = []
            continue
        bars: list[PriceBar] = []
        for idx, row in hist.iterrows():
            close = row.get("Close")
            adj = row.get("Adj Close", close)
            if close is None or adj is None:
                continue
            bars.append(
                PriceBar(
                    day=idx.date(),
                    close=Decimal(str(round(float(close), 6))),
                    adj_close=Decimal(str(round(float(adj), 6))),
                    volume=int(row.get("Volume") or 0),
                )
            )
        out[symbol] = bars
    return out


def upsert_prices(db: Session, company: Company, bars: Iterable[PriceBar]) -> int:
    """Upsert por (company_id, date). Devuelve barras escritas."""
    written = 0
    for bar in bars:
        values = {
            "company_id": company.id,
            "date": bar.day,
            "open": bar.close,
            "high": bar.close,
            "low": bar.close,
            "close": bar.close,
            "adj_close": bar.adj_close,
            "volume": bar.volume,
            "source": "yfinance",
        }
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            stmt = pg_insert(MarketPrice).values(**values)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_market_price_company_date",
                set_={
                    "close": stmt.excluded.close,
                    "adj_close": stmt.excluded.adj_close,
                    "volume": stmt.excluded.volume,
                    "source": stmt.excluded.source,
                },
            )
            db.execute(stmt)
        else:
            existing = db.scalar(
                select(MarketPrice).where(
                    MarketPrice.company_id == company.id,
                    MarketPrice.date == bar.day,
                )
            )
            if existing is not None:
                existing.close = bar.close
                existing.adj_close = bar.adj_close
                existing.volume = bar.volume
                existing.source = "yfinance"
            else:
                db.add(MarketPrice(**values))
        written += 1
    return written


def momentum_from_series(series: Sequence[tuple[date, Decimal]], days: int) -> Decimal | None:
    """Rentabilidad entre el ultimo adj_close y el mas cercano a `days` atras.

    `series` ordenada ascendente por fecha. None si no hay datos suficientes.
    """
    if len(series) < 2:
        return None
    last_day, last_px = series[-1]
    target = last_day - timedelta(days=days)
    past = [(d, p) for d, p in series if d <= target]
    if not past:
        return None
    past_day, past_px = past[-1]
    # Exigimos que el punto pasado este razonablemente cerca del objetivo
    # (+-20 dias) para no vender como 6m un retorno de 2 semanas.
    if abs((past_day - target).days) > 20:
        return None
    if past_px <= 0:
        return None
    return (last_px - past_px) / past_px


def compute_momentum_metrics(
    db: Session,
    companies: Sequence[Company],
    *,
    as_of: date,
) -> dict[str, int]:
    """Calcula y persiste momentum_6m/12m en calculated_metrics."""
    tenant_id = db.info.get("tenant_id")
    stats = {"momentum_6m": 0, "momentum_12m": 0, "skipped": 0}
    for company in companies:
        rows = db.execute(
            select(MarketPrice.date, MarketPrice.adj_close)
            .where(MarketPrice.company_id == company.id)
            .order_by(MarketPrice.date)
        ).all()
        series = [(d, Decimal(str(p))) for d, p in rows if p is not None and p > 0]
        if len(series) < MIN_BARS_6M:
            stats["skipped"] += 1
            continue
        for metric, days in MOMENTUM_WINDOWS.items():
            if len(series) < (MIN_BARS_12M if days > 126 else MIN_BARS_6M):
                continue
            value = momentum_from_series(series, days)
            if value is None:
                continue
            existing = db.scalar(
                select(CalculatedMetric).where(
                    CalculatedMetric.tenant_id == tenant_id,
                    CalculatedMetric.company_id == company.id,
                    CalculatedMetric.metric == metric,
                    CalculatedMetric.period == as_of.isoformat(),
                    CalculatedMetric.definition_version == METRIC_VERSION,
                )
            )
            if existing is not None:
                existing.value = value
            else:
                db.add(
                    CalculatedMetric(
                        tenant_id=tenant_id,
                        company_id=company.id,
                        metric=metric,
                        value=value,
                        unit="decimal",
                        period=as_of.isoformat(),
                        fiscal_year=as_of.year,
                        status="ok",
                        definition_version=METRIC_VERSION,
                        formula=f"adj_close(t)/adj_close(t-{days}d) - 1 sobre market_prices (yfinance)",
                        numerator=None,
                        denominator=None,
                        source_fact_ids=[],
                        calculation_trace={"window_days": days, "as_of": as_of.isoformat()},
                    )
                )
            stats[metric] += 1
    return stats


def latest_run_top_companies(db: Session, *, top_n: int = 40) -> list[Company]:
    """Top-N aprobadas del ultimo run completado del embudo."""
    run = db.scalar(
        select(ProPickRun)
        .where(ProPickRun.status == "completed")
        .order_by(desc(ProPickRun.id))
        .limit(1)
    )
    if run is None:
        return []
    rows = db.execute(
        select(Company)
        .join(ProPickCandidate, ProPickCandidate.company_id == Company.id)
        .where(ProPickCandidate.run_id == run.id, ProPickCandidate.passed.is_(True))
        .order_by(ProPickCandidate.rank)
        .limit(top_n)
    ).scalars().all()
    return list(rows)


def refresh_propicks_prices(
    db: Session,
    *,
    top_n: int = 40,
    period: str = "1y",
    fetcher: Callable[..., dict[str, list[PriceBar]]] = fetch_history_yfinance,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Job F2: precios diarios + momentum para el top-N del ultimo run."""
    as_of = as_of or date.today()
    companies = latest_run_top_companies(db, top_n=top_n)
    if not companies:
        return {"status": "skipped", "reason": "no completed propick run", "companies": 0}
    symbols = {yahoo_symbol(c): c for c in companies}
    history = fetcher(list(symbols), period=period)
    bars_written = 0
    covered: list[Company] = []
    for symbol, company in symbols.items():
        bars = history.get(symbol) or []
        if not bars:
            continue
        bars_written += upsert_prices(db, company, bars)
        covered.append(company)
    momentum = compute_momentum_metrics(db, covered, as_of=as_of)
    db.commit()
    return {
        "status": "ok",
        "companies": len(companies),
        "covered": len(covered),
        "bars_written": bars_written,
        "momentum": momentum,
        "as_of": as_of.isoformat(),
    }
