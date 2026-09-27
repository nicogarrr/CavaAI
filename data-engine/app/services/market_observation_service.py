"""Free, dated FRED observations; no query-time vendor traffic."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MarketObservation
from app.services.connectors.fred import FREDClient

FRED_SERIES = {
    "mortgage_30y_us": ("MORTGAGE30US", "porcentaje", 14),
    "treasury_10y_us": ("DGS10", "porcentaje", 5),
    "treasury_2y_us": ("DGS2", "porcentaje", 5),
    "breakeven_10y_us": ("T10YIE", "porcentaje", 5),
    "high_yield_spread_us": ("BAMLH0A0HYM2", "puntos porcentuales", 5),
    "vix_us": ("VIXCLS", "índice", 5),
}


def parse_points(rows: list[dict]) -> list[tuple[date, Decimal]]:
    points: dict[date, Decimal] = {}
    for row in rows:
        try:
            day = date.fromisoformat(str(row["date"]))
            value = Decimal(str(row["value"]))
            if value.is_finite():
                points[day] = value
        except (KeyError, TypeError, ValueError, InvalidOperation):
            continue
    return sorted(points.items())


def store_series(db: Session, key: str, rows: list[dict], fetched_at: datetime) -> dict:
    if key not in FRED_SERIES or fetched_at.tzinfo is None:
        raise ValueError("Serie u hora inválida")
    series_id, unit, _ = FRED_SERIES[key]
    added = 0
    revisions = 0
    for day, value in parse_points(rows):
        if day > fetched_at.astimezone(UTC).date():
            continue
        previous = db.scalar(
            select(MarketObservation).where(
                MarketObservation.metric_key == key,
                MarketObservation.observation_date == day,
                MarketObservation.vintage == "initial",
            )
        )
        if previous and previous.value == value:
            continue
        if previous:
            # A revision is not silently substituted into historical evidence.
            revisions += 1
            vintage = fetched_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
            status = "revision_pending"
        else:
            vintage = "initial"
            status = "observed"
        if db.scalar(
            select(MarketObservation.id).where(
                MarketObservation.metric_key == key,
                MarketObservation.observation_date == day,
                MarketObservation.vintage == vintage,
            )
        ):
            continue
        db.add(
            MarketObservation(
                metric_key=key,
                geography="US",
                observation_date=day,
                value=value,
                unit=unit,
                source="FRED",
                source_url=f"https://fred.stlouisfed.org/series/{series_id}",
                fetched_at=fetched_at,
                vintage=vintage,
                status=status,
            )
        )
        db.flush()
        added += 1
    return {"added": added, "revisions_pending": revisions}


async def refresh_fred(db: Session, client: FREDClient | None = None) -> dict:
    client = client or FREDClient()
    outcome: dict = {"series": {}, "errors": {}}
    for key, (series_id, _, _) in FRED_SERIES.items():
        try:
            payload = await client.series_csv(series_id, limit=20)
            if not parse_points(payload.get("observations") or []):
                outcome["errors"][key] = "sin datos"
                continue
            outcome["series"][key] = store_series(db, key, payload["observations"], datetime.now(UTC))
            db.commit()
        except (httpx.HTTPError, ValueError, KeyError, TypeError, RuntimeError) as exc:
            db.rollback()
            outcome["errors"][key] = type(exc).__name__
    return outcome
