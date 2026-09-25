from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from xml.etree import ElementTree

import httpx


@dataclass(frozen=True)
class ECBRates:
    rate_date: date
    # Multipliers convert an amount in the key currency into base_currency.
    rates: dict[str, Decimal]


class ECBClient:
    url = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"

    async def conversion_rates(
        self, *, base_currency: str, quote_currencies: set[str]
    ) -> ECBRates:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(self.url)
            response.raise_for_status()
        root = ElementTree.fromstring(response.content)
        rate_date: date | None = None
        per_eur: dict[str, Decimal] = {"EUR": Decimal("1")}
        for element in root.iter():
            if element.attrib.get("time"):
                rate_date = date.fromisoformat(element.attrib["time"])
            currency = element.attrib.get("currency")
            rate = element.attrib.get("rate")
            if currency and rate:
                per_eur[currency.upper()] = Decimal(rate)
        base = base_currency.upper()
        if rate_date is None or base not in per_eur:
            raise RuntimeError(f"ECB does not provide the base currency {base}")
        rates = {}
        for quote in quote_currencies:
            normalized = quote.upper()
            if normalized not in per_eur:
                continue
            # ECB publishes units of each currency for one EUR. Therefore an
            # amount in quote converts to base by base_per_eur / quote_per_eur.
            rates[normalized] = per_eur[base] / per_eur[normalized]
        rates[base] = Decimal("1")
        return ECBRates(rate_date=rate_date, rates=rates)


# ---------------------------------------------------------------------------
# SDW (Statistical Data Warehouse): series macro del BCE, REST SDMX 2.1,
# gratuito y sin clave. Formato CSV plano (?format=csvdata).
# ---------------------------------------------------------------------------

SDW_BASE = "https://data-api.ecb.europa.eu/service/data"

# indicator -> (clave SDMX, nombre legible, unidad)
ECB_MACRO_SERIES: dict[str, tuple[str, str, str]] = {
    "ecb_mrr": (
        "FM/B.U2.EUR.4F.KR.MRR_FR.LEV",
        "Tipo principal de refinanciacion (BCE)",
        "%",
    ),
    "ecb_dfr": (
        "FM/B.U2.EUR.4F.KR.DFR.LEV",
        "Facilidad de deposito (BCE)",
        "%",
    ),
    "ecb_hicp_yoy": (
        "ICP/M.U2.N.000000.4.ANR",
        "Inflacion HICP zona euro (interanual)",
        "%",
    ),
    "ecb_gdp_yoy": (
        "MNA/Q.Y.I8.W2.S1.S1.B.B1GQ._Z._Z._Z.EUR.LR.GY",
        "PIB zona euro (interanual)",
        "%",
    ),
}


@dataclass(frozen=True)
class ECBMacroPoint:
    indicator: str
    name: str
    unit: str
    date: str
    value: Decimal


def parse_sdw_csv(text: str, indicator: str, name: str, unit: str) -> list[ECBMacroPoint]:
    """CSV plano del SDW: cabecera con TIME_PERIOD y OBS_VALUE; una fila por
    observacion. Devuelve los puntos en orden temporal ascendente."""
    import csv
    import io

    reader = csv.DictReader(io.StringIO(text))
    points: list[ECBMacroPoint] = []
    for row in reader:
        period = (row.get("TIME_PERIOD") or "").strip()
        raw = (row.get("OBS_VALUE") or "").strip()
        if not period or not raw:
            continue
        try:
            value = Decimal(raw)
        except Exception:
            continue
        # Decimal('NaN')/Infinity pasan el parse y luego rompen la
        # serializacion JSON del endpoint (float('nan') no es JSON valido).
        if not value.is_finite():
            continue
        points.append(
            ECBMacroPoint(indicator=indicator, name=name, unit=unit, date=period, value=value)
        )
    return points


class ECBSDWClient:
    """Series macro del BCE via SDW. Degrada a lista vacia por serie si el
    SDW no responde: el endpoint agrega lo que haya, nunca inventa."""

    base_url = SDW_BASE

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self.client = client

    async def series(self, sdmx_key: str, *, last: int = 2) -> str:
        url = f"{self.base_url}/{sdmx_key}"
        params = {"format": "csvdata", "lastNObservations": str(last)}
        if self.client is not None:
            response = await self.client.get(url, params=params)
        else:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(url, params=params)
        response.raise_for_status()
        return response.text

    async def macro_points(self, *, last: int = 2) -> list[ECBMacroPoint]:
        points: list[ECBMacroPoint] = []
        for indicator, (key, name, unit) in ECB_MACRO_SERIES.items():
            try:
                text = await self.series(key, last=last)
            except Exception:
                continue
            points.extend(parse_sdw_csv(text, indicator, name, unit))
        return points
