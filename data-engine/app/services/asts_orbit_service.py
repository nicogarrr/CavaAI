"""Exploratory orbital-element trends; never deployment telemetry."""
from __future__ import annotations

from datetime import datetime
from math import pi, isfinite

EARTH_MU_KM3_S2 = 398600.4418
MAX_EPOCHS_PER_OBJECT = 32
MIN_SPACING_HOURS = 2
MIN_TREND_HOURS = 24


def sma_km(mean_motion_rev_day: float) -> float:
    """Kepler a=(mu/(2*pi*n/86400)^2)^(1/3), n in revolutions/day."""
    if not isfinite(mean_motion_rev_day) or not (0 < mean_motion_rev_day < 20):
        raise ValueError("Invalid mean motion")
    return (EARTH_MU_KM3_S2 / (2 * pi * mean_motion_rev_day / 86400) ** 2) ** (1 / 3)


def append_history(previous: dict | None, catalog: list[dict]) -> dict[str, list[dict]]:
    """Unique NORAD+epoch, not fetch time; only comparable consecutive epochs."""
    prior = previous if isinstance(previous, dict) else {}
    result: dict[str, list[dict]] = {}
    for row in catalog:
        key = str(row["norad_cat_id"])
        existing = prior.get(key)
        samples = [item for item in existing if isinstance(item, dict) and item.get("epoch") and isinstance(item.get("sma_km"), (int, float))] if isinstance(existing, list) else []
        epoch = datetime.fromisoformat(row["epoch"])
        sample = {
            "epoch": epoch.isoformat(), "sma_km": round(sma_km(float(row["mean_motion"])), 4),
            "bstar": row.get("bstar"), "mean_motion_dot": row.get("mean_motion_dot"),
        }
        by_epoch = {item["epoch"]: item for item in samples}
        by_epoch[sample["epoch"]] = sample
        result[key] = [by_epoch[date] for date in sorted(by_epoch)[-MAX_EPOCHS_PER_OBJECT:]]
    # Retain prior series for objects temporarily absent from the current feed,
    # but never expose them in the current-object API without a fresh row.
    for key, series in prior.items():
        if key not in result and isinstance(series, list):
            result[key] = series[-MAX_EPOCHS_PER_OBJECT:]
    return result


def orbit_signal(history: list[dict]) -> dict:
    """Compare separated epochs; thresholds are screening heuristics, not events."""
    samples = sorted(history, key=lambda item: item["epoch"])
    if len(samples) < 3:
        return {"status": "sin historial suficiente", "delta_sma_km": None, "hours": None}
    latest = samples[-1]
    latest_time = datetime.fromisoformat(latest["epoch"])
    # Avoid a much older baseline: changes over weeks cannot be attributed to one event.
    baselines = [item for item in samples[:-1] if
                 MIN_TREND_HOURS <= (latest_time - datetime.fromisoformat(item["epoch"])).total_seconds() / 3600 <= 72]
    if not baselines:
        return {"status": "sin historial comparable", "delta_sma_km": None, "hours": None}
    baseline = baselines[0]
    interval_hours = (latest_time - datetime.fromisoformat(baseline["epoch"])).total_seconds() / 3600
    window = [item for item in samples if item["epoch"] >= baseline["epoch"]]
    if len(window) < 3 or any(
        (datetime.fromisoformat(right["epoch"]) - datetime.fromisoformat(left["epoch"])).total_seconds() / 3600 < MIN_SPACING_HOURS
        for left, right in zip(window, window[1:])
    ):
        return {"status": "sin historial comparable", "delta_sma_km": None, "hours": None}
    delta = round(float(latest["sma_km"]) - float(baseline["sma_km"]), 4)
    # A >=2 km decline in a 24-72h interval merits investigation only.
    # BSTAR/mm-dot are fit parameters, not independent confirmation.
    status = "firma compatible con variación orbital; revisar fuentes" if delta <= -2 else (
        "variación a revisar" if abs(delta) >= 1 else "sin variación relevante")
    return {"status": status, "delta_sma_km": delta, "hours": round(interval_hours, 1)}
