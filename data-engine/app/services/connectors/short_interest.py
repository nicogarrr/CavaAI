"""Senales de posicion corta (FINRA) y volatilidad (VIX, CBOE via Yahoo).

Dos vendors gratuitos y sin clave que faltaban en CavaAI:

* **FINRA — volumen corto diario (RegSHO)**: ficheros de texto publicados en
  ``cdn.finra.org/equity/regsho/daily/CNMSshvol{AAAAMMDD}.txt`` con columnas
  ``Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market``. Es el dato
  gratuito y por ticker que mejor aproxima la presion de ventas en corto.
* **FINRA — posicion corta consolidada (quincenal)**: ``api.finra.org`` sirve el
  dataset ``consolidatedShortInterest`` (short interest, days-to-cover). Ojo: el
  filtro ``queryFilter`` se ignora en acceso anonimo (verificado en vivo), asi
  que el ticker se localiza con una busqueda binaria acotada sobre ``offset``
  (el dataset llega ordenado por ``symbolCode``). Nunca se hacen mas de
  ``max_requests`` peticiones.
* **VIX (^VIX, indice CBOE)**: chart API de Yahoo (mismo patron que
  ``app/api/routes/market.py``). Yahoo es un agregador no oficial: el VIX es un
  indice publico, pero el precio sirve solo como señal, nunca como referencia
  autoritativa.

Idea de estructura inspirada en los conectores gratuitos de
TauricResearch/TradingAgents (Apache-2.0); implementacion propia para CavaAI
con ``httpx`` inyectable (tests hermeticos con ``MockTransport``). Ninguna
funcion de red lanza excepciones: degradan a ``None``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

FINRA_REGSHO_DAILY_URL = (
    "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{yyyymmdd}.txt"
)
FINRA_SHORT_INTEREST_URL = (
    "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"
)
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
VIX_SYMBOL = "^VIX"

REGSHO_HEADER = "Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market"

# Umbrales de señal (documentados y unitarios; nada de magia).
SHORT_VOLUME_RATIO_ALERT = 0.55  # >55% del volumen del dia fue corto
DAYS_TO_COVER_ALERT = 4.0  # ~1 semana de bolas cortas
SHORT_INTEREST_CHANGE_ALERT = 0.10  # +10% de crecimiento de la posicion corta
VIX_ELEVATED = 20.0
VIX_STRESS = 30.0

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------- FINRA: volumen corto diario (RegSHO) ----------------


def parse_regsho_daily(text: str, symbol: str) -> dict | None:
    """Extrae la fila de `symbol` del fichero RegSHO diario (texto con `|`).

    Devuelve ``None`` si el ticker no cotizo ese dia o el fichero esta vacio.
    Lineas malformadas se ignoran en vez de romper el parseo.
    """
    wanted = symbol.strip().upper()
    if not wanted or not text:
        return None
    for line in text.splitlines():
        parts = [part.strip() for part in line.strip().split("|")]
        if len(parts) < 6 or parts[0] == "Date" or parts[1].upper() != wanted:
            continue
        short_volume = _to_float(parts[2])
        short_exempt = _to_float(parts[3])
        total_volume = _to_float(parts[4])
        if short_volume is None or total_volume is None:
            continue
        yyyymmdd = parts[0]
        trade_date = (
            f"{yyyymmdd[0:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]}"
            if len(yyyymmdd) == 8 and yyyymmdd.isdigit()
            else yyyymmdd
        )
        ratio = (short_volume / total_volume) if total_volume > 0 else None
        return {
            "symbol": wanted,
            "date": trade_date,
            "short_volume": int(short_volume),
            "short_exempt_volume": int(short_exempt or 0),
            "total_volume": int(total_volume),
            "short_volume_ratio": ratio,
            "markets": parts[5],
            "source": "finra_regsho",
            "source_url": FINRA_REGSHO_DAILY_URL.format(yyyymmdd=yyyymmdd),
        }
    return None


async def fetch_short_volume(
    symbol: str,
    trade_date: date | None = None,
    *,
    client: httpx.AsyncClient | None = None,
    lookback_days: int = 7,
) -> dict | None:
    """Ultimo volumen corto diario de `symbol` publicado por FINRA.

    El fichero del dia se publica tras el cierre y no hay dato en fines de
    semana/festivos: se retrocede hasta `lookback_days` dias hasta encontrar el
    ultimo fichero que contiene al ticker. ``None`` si no hay dato (sin excepciones).
    """
    day = trade_date or datetime.now(UTC).date()
    for offset in range(lookback_days + 1):
        current = day - timedelta(days=offset)
        yyyymmdd = current.strftime("%Y%m%d")
        url = FINRA_REGSHO_DAILY_URL.format(yyyymmdd=yyyymmdd)
        try:
            if client is not None:
                response = await client.get(url, headers=dict(_HEADERS))
            else:
                async with httpx.AsyncClient(timeout=30, headers=dict(_HEADERS)) as owned:
                    response = await owned.get(url)
        except httpx.HTTPError:
            return None
        if response.status_code != 200:
            continue
        row = parse_regsho_daily(response.text, symbol)
        if row is not None:
            return row
    return None


# ---------------- FINRA: posicion corta consolidada (quincenal) ----------------


def parse_short_interest_record(record: dict, symbol: str) -> dict | None:
    """Normaliza una fila del dataset `consolidatedShortInterest` de FINRA."""
    if not isinstance(record, dict):
        return None
    code = str(record.get("symbolCode") or "").upper()
    if code != symbol.strip().upper():
        return None
    current = _to_float(record.get("currentShortPositionQuantity"))
    previous = _to_float(record.get("previousShortPositionQuantity"))
    avg_volume = _to_float(record.get("averageDailyVolumeQuantity"))
    days_to_cover = _to_float(record.get("daysToCoverQuantity"))
    if days_to_cover is None and current is not None and avg_volume:
        days_to_cover = current / avg_volume
    change_pct = (
        (current - previous) / previous
        if current is not None and previous
        else None
    )
    return {
        "symbol": code,
        "issue_name": record.get("issueName"),
        "settlement_date": record.get("settlementDate"),
        "short_interest": int(current) if current is not None else None,
        "previous_short_interest": int(previous) if previous is not None else None,
        "change_pct": change_pct,
        "average_daily_volume": int(avg_volume) if avg_volume is not None else None,
        "days_to_cover": days_to_cover,
        "market_class": record.get("marketClassCode"),
        "source": "finra_short_interest",
        "source_url": FINRA_SHORT_INTEREST_URL,
    }


async def _short_interest_page(
    offset: int,
    limit: int,
    client: httpx.AsyncClient | None,
) -> list | None:
    params = {"limit": limit, "offset": offset, "sortField": "symbolCode", "sortOrder": "asc"}
    try:
        if client is not None:
            response = await client.get(
                FINRA_SHORT_INTEREST_URL, params=params, headers=dict(_HEADERS)
            )
        else:
            async with httpx.AsyncClient(timeout=30, headers=dict(_HEADERS)) as owned:
                response = await owned.get(FINRA_SHORT_INTEREST_URL, params=params)
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    data = response.json()
    return data if isinstance(data, list) else None


async def fetch_short_interest(
    symbol: str,
    *,
    client: httpx.AsyncClient | None = None,
    page_size: int = 200,
    max_requests: int = 12,
) -> dict | None:
    """Posicion corta consolidada (quincenal) de `symbol`; ``None`` si no hay dato.

    Acceso anonimo: el ``queryFilter`` de FINRA se ignora (verificado en vivo),
    asi que se hace una busqueda binaria acotada por indice de pagina (multiplos
    de `page_size`) aprovechando que el dataset llega ordenado por
    ``symbolCode``. Nunca mas de `max_requests` peticiones y nunca una excepcion
    hacia el llamante.
    """
    wanted = symbol.strip().upper()
    if not wanted or page_size < 1 or max_requests < 1:
        return None

    budget = max_requests
    seen: dict[int, list] = {}

    async def page(index: int) -> list | None:
        nonlocal budget
        if index in seen:
            return seen[index]
        if budget <= 0:
            return None
        budget -= 1
        rows = await _short_interest_page(index * page_size, page_size, client)
        if rows:
            seen[index] = rows
        return rows

    def find(rows: list) -> dict | None:
        for row in rows:
            parsed = parse_short_interest_record(row, wanted)
            if parsed is not None:
                return parsed
        return None

    # 1) Busqueda exponencial del primer indice de pagina cuyo ultimo codigo
    #    alcanza al ticker (o de una pagina vacia = fin del dataset).
    low, high = 0, 1
    while budget > 0:
        rows = await page(high)
        if not rows:
            break
        if str(rows[-1].get("symbolCode") or "").upper() >= wanted:
            break
        low, high = high, high * 2

    # 2) Busqueda binaria dentro de [low, high].
    while low < high and budget > 0:
        mid = (low + high) // 2
        rows = await page(mid)
        if not rows:
            high = mid
            continue
        hit = find(rows)
        if hit is not None:
            return hit
        if wanted < str(rows[0].get("symbolCode") or "").upper():
            high = mid
        else:
            low = mid + 1

    # 3) El ticker puede haber caido en una pagina frontera ya descargada.
    for rows in seen.values():
        hit = find(rows)
        if hit is not None:
            return hit
    return None


# ---------------- VIX (^VIX via Yahoo) ----------------


def vix_regime(vix: float | None) -> str:
    """Regimen de volatilidad a partir del nivel del VIX (bordes inclusivos)."""
    if vix is None:
        return "unknown"
    if vix >= VIX_STRESS:
        return "stress"
    if vix >= VIX_ELEVATED:
        return "elevated"
    return "calm"


def parse_vix_chart(payload: dict) -> dict | None:
    """Ultimo cierre del ^VIX desde la respuesta de la chart API de Yahoo."""
    try:
        result = payload["chart"]["result"][0]
        closes = [
            value
            for value in result["indicators"]["quote"][0]["close"]
            if value is not None
        ]
    except (KeyError, IndexError, TypeError):
        return None
    if len(closes) < 2:
        return None
    last, previous = closes[-1], closes[-2]
    change = last - previous
    change_percent = (change / previous) * 100 if previous else 0.0
    return {
        "symbol": VIX_SYMBOL,
        "price": round(float(last), 2),
        "change": round(float(change), 2),
        "change_percent": round(float(change_percent), 2),
        "regime": vix_regime(float(last)),
        "source": "yahoo_finance",
        "source_url": "https://finance.yahoo.com/quote/%5EVIX",
    }


async def fetch_vix(*, client: httpx.AsyncClient | None = None) -> dict | None:
    """Ultimo VIX desde Yahoo (gratuita, sin key); ``None`` si falla la red."""
    url = YAHOO_CHART_URL.format(symbol=VIX_SYMBOL.replace("^", "%5E"))
    params = {"range": "5d", "interval": "1d"}
    try:
        if client is not None:
            response = await client.get(url, params=params, headers=dict(_HEADERS))
        else:
            async with httpx.AsyncClient(timeout=15, headers=dict(_HEADERS)) as owned:
                response = await owned.get(url, params=params)
        if response.status_code != 200:
            return None
        return parse_vix_chart(response.json())
    except (httpx.HTTPError, ValueError, TypeError):
        return None


# ---------------- Senales ----------------


def stress_signals(
    *,
    vix: dict | None = None,
    short_volume: dict | None = None,
    short_interest: dict | None = None,
) -> list[dict]:
    """Senales de mercado a partir de los datos disponibles (sin inventar).

    Formato homogeneo con `app.services.insider_service.detect_signals`:
    ``{signal, ticker, severity, detail, metric_value, threshold, source_url}``.
    Sin datos no hay senales: nunca se fabrica una señal.
    """
    signals: list[dict] = []

    if vix and vix.get("price") is not None:
        level = float(vix["price"])
        regime = vix_regime(level)
        if regime in {"elevated", "stress"}:
            signals.append(
                {
                    "signal": "vix_stress" if regime == "stress" else "vix_elevated",
                    "ticker": None,
                    "severity": "high" if regime == "stress" else "medium",
                    "detail": f"VIX {level} ({regime})",
                    "metric_value": level,
                    "threshold": VIX_STRESS if regime == "stress" else VIX_ELEVATED,
                    "source_url": vix.get("source_url"),
                }
            )

    if short_volume and short_volume.get("short_volume_ratio") is not None:
        ratio = float(short_volume["short_volume_ratio"])
        if ratio >= SHORT_VOLUME_RATIO_ALERT:
            signals.append(
                {
                    "signal": "high_short_volume",
                    "ticker": short_volume.get("symbol"),
                    "severity": "medium",
                    "detail": (
                        f"{short_volume.get('symbol')}: {ratio:.0%} del volumen "
                        f"del {short_volume.get('date')} fue corto (FINRA)"
                    ),
                    "metric_value": round(ratio, 4),
                    "threshold": SHORT_VOLUME_RATIO_ALERT,
                    "source_url": short_volume.get("source_url"),
                }
            )

    if short_interest:
        days_to_cover = short_interest.get("days_to_cover")
        change_pct = short_interest.get("change_pct")
        if days_to_cover is not None and float(days_to_cover) >= DAYS_TO_COVER_ALERT:
            signals.append(
                {
                    "signal": "high_days_to_cover",
                    "ticker": short_interest.get("symbol"),
                    "severity": "medium",
                    "detail": (
                        f"{short_interest.get('symbol')}: {float(days_to_cover):.1f} dias "
                        f"para cubrir la posicion corta (FINRA)"
                    ),
                    "metric_value": round(float(days_to_cover), 2),
                    "threshold": DAYS_TO_COVER_ALERT,
                    "source_url": short_interest.get("source_url"),
                }
            )
        if change_pct is not None and float(change_pct) >= SHORT_INTEREST_CHANGE_ALERT:
            signals.append(
                {
                    "signal": "short_interest_buildup",
                    "ticker": short_interest.get("symbol"),
                    "severity": "medium",
                    "detail": (
                        f"{short_interest.get('symbol')}: la posicion corta crece un "
                        f"{float(change_pct):.0%} ({short_interest.get('settlement_date')})"
                    ),
                    "metric_value": round(float(change_pct), 4),
                    "threshold": SHORT_INTEREST_CHANGE_ALERT,
                    "source_url": short_interest.get("source_url"),
                }
            )

    return signals


async def market_stress_report(
    ticker: str | None = None,
    *,
    client: httpx.AsyncClient | None = None,
) -> dict:
    """Foto de senales de mercado (VIX + posicion corta FINRA). Nunca lanza.

    ``status``: ``ok`` (todo disponible), ``partial`` (alguna fuente fallo) o
    ``unavailable`` (ninguna fuente respondio).
    """
    vix = await fetch_vix(client=client)
    short_volume = None
    short_interest = None
    if ticker:
        short_volume = await fetch_short_volume(ticker, client=client)
        short_interest = await fetch_short_interest(ticker, client=client)

    sources = [vix is not None]
    if ticker:
        sources.append(short_volume is not None or short_interest is not None)
    available = sum(1 for source in sources if source)
    status = (
        "unavailable"
        if available == 0
        else ("ok" if available == len(sources) else "partial")
    )
    return {
        "status": status,
        "ticker": ticker.upper() if ticker else None,
        "vix": vix,
        "short_volume": short_volume,
        "short_interest": short_interest,
        "signals": stress_signals(
            vix=vix, short_volume=short_volume, short_interest=short_interest
        ),
        "note": (
            "FINRA (volumen/posicion corta) es una fuente autoritativa de reporte "
            "regulatorio; el VIX via Yahoo es un agregador no oficial y solo sirve "
            "como señal de regimen de volatilidad."
        ),
    }
