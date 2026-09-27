"""Datos macro del BCE via SDW (gratuito, sin clave). Cache en memoria de 1h:
las series cambian como mucho a diario (tipos) o mensual/trimestral."""

from __future__ import annotations

import time

from fastapi import APIRouter

from app.services.connectors.ecb import ECBSDWClient

router = APIRouter()

_CACHE_TTL_SECONDS = 3600
_cache: dict[str, tuple[float, list[dict]]] = {}


def _to_item(point) -> dict:
    return {
        "source": "ecb",
        "indicator": point.indicator,
        "name": point.name,
        "value": float(point.value),
        "unit": point.unit,
        "date": point.date,
    }


@router.get("/ecb")
async def ecb_macro() -> dict:
    """Ultimas observaciones de las series macro clave del BCE.

    Shape alineado con el MacroData del frontend (source/indicator/name/
    value/unit/date) mas change/previousValue cuando hay 2 observaciones.
    Series caidas simplemente no aparecen; nunca se inventan valores.
    """
    now = time.time()
    cached = _cache.get("ecb")
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return {"items": cached[1], "cached": True}

    client = ECBSDWClient()
    points = await client.macro_points(last=2)
    latest: dict[str, dict] = {}
    for point in points:
        item = _to_item(point)
        current = latest.get(point.indicator)
        if current is None:
            latest[point.indicator] = item
            continue
        # Los puntos llegan ascendentes: el primero es previousValue.
        item["previousValue"] = current["value"]
        item["change"] = round(item["value"] - current["value"], 4)
        base = abs(current["value"])
        if base > 0:
            item["changePercent"] = round(
                (item["value"] - current["value"]) / base * 100, 2
            )
        latest[point.indicator] = item
    items = list(latest.values())
    _cache["ecb"] = (now, items)
    return {"items": items, "cached": False}
