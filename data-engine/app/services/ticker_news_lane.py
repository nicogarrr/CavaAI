"""Carril de noticias por ticker independiente de GDELT.

GDELT (tier gratuito, ~1 req / 5 s por IP) devuelve 429 en la mayoria de las
consultas y dejaba a empresas como ASTS o SPCX sin titulares durante dias. Este
carril usa dos fuentes gratuitas sin clave, por ticker, con pacing propio:

- Yahoo Finance RSS por simbolo (solo cotizadas en EEUU: el simbolo de otras
  bolsas necesita sufijo de mercado que aqui no se conoce, asi que no se
  adivina).
- Google News RSS por nombre de empresa y ticker. Solo se guardan titulares
  cuya pista de texto cita a la empresa (misma regla de evidencia que
  NewsService), porque la busqueda es amplia.

Fuente y fecha son las reales del feed; el dedupe por URL lo hace
NewsService. Nada se inventa: sin fecha, el item conserva published_at None.
"""

from __future__ import annotations

import dataclasses
import re
from urllib.parse import quote_plus

from app.services.connectors.base import ConnectorItem, ConnectorResult

US_EXCHANGE_RE = re.compile(r"NASDAQ|NYSE|AMEX|ARCA|BATS|CBOE", re.IGNORECASE)
# Empresas que Nico sigue de cerca: siempre entran en el carril rapido.
PRIORITY_TICKERS = frozenset({"ASTS", "SPCX"})
_TICKER_RE = re.compile(r"^[A-Z]{1,5}$")
_PUBLISHER_RE = re.compile(r"^(?P<title>.+?)\s+-\s+(?P<publisher>[^-]{2,60})$")


def is_us_listed(company) -> bool:
    ticker = (getattr(company, "ticker", "") or "").upper()
    exchange = getattr(company, "exchange", "") or ""
    return bool(_TICKER_RE.match(ticker)) and bool(US_EXCHANGE_RE.search(exchange))


def yahoo_feed_url(ticker: str) -> str:
    return (
        "https://feeds.finance.yahoo.com/rss/2.0/headline"
        f"?s={quote_plus(ticker.upper())}&region=US&lang=en-US"
    )


def google_feed_url(company, *, lang: str = "en") -> str:
    name = re.sub(r"\s+(inc|corp|corporation|co|ltd|plc|holdings?)\.?$", "", company.name or "", flags=re.I)
    query = f'"{name.strip()}" OR {company.ticker.upper()}' if name.strip() else company.ticker.upper()
    hl, gl, ceid = ("es", "ES", "ES:es") if lang == "es" else ("en-US", "US", "US:en")
    return (
        f"https://news.google.com/rss/search?q={quote_plus(query)}"
        f"&hl={hl}&gl={gl}&ceid={ceid}"
    )


def label_yahoo(result: ConnectorResult) -> ConnectorResult:
    """Fuente legible y estable: el titulo del feed es 'Yahoo! Finance: X News'."""
    result.items = [dataclasses.replace(item, source="Yahoo Finance") for item in result.items]
    return result


def label_google(result: ConnectorResult, company, evidence_level) -> ConnectorResult:
    """Fuente = medio real (sufijo ' - Medio' del titular) y filtro de evidencia."""
    kept: list[ConnectorItem] = []
    for item in result.items:
        text = f"{item.title} {item.summary}"
        if evidence_level(company.ticker, company.name, text) <= 0:
            continue
        match = _PUBLISHER_RE.match(item.title)
        if match:
            item = dataclasses.replace(
                item, title=match.group("title").strip(), source=match.group("publisher").strip()
            )
        else:
            item = dataclasses.replace(item, source="Google News")
        kept.append(item)
    result.items = kept
    return result
