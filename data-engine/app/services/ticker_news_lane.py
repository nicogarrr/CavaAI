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
import time
from collections.abc import Callable
from urllib.parse import quote_plus

from app.services.connectors.base import ConnectorItem, ConnectorResult

US_EXCHANGE_RE = re.compile(r"NASDAQ|NYSE|AMEX|ARCA|BATS|CBOE", re.IGNORECASE)
# Empresas que Nico sigue de cerca: siempre entran en el carril rapido.
PRIORITY_TICKERS = frozenset({"ASTS", "SPCX"})
# Alias verificados a mano por empresa: las noticias reales citan la marca y no
# el ticker ("SpaceX compra espectro..."). Solo marcas propias de esa empresa;
# nada de terminos de sector ("satelite", "espacio") ni de competidores.
VERIFIED_ALIASES: dict[str, tuple[str, ...]] = {
    "SPCX": ("SpaceX", "Space Exploration Technologies", "Starlink"),
    "ASTS": ("AST SpaceMobile", "SpaceMobile", "BlueBird"),
}
_NAME_NOISE = frozenset({
    "inc", "corp", "corporation", "co", "company", "ltd", "plc", "sa", "nv", "ag",
    "the", "group", "holdings", "holding", "limited", "sme", "s.a.",
})
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


def _name_phrase(name: str | None) -> str | None:
    words = [w for w in re.split(r"\s+", (name or "").strip()) if w]
    kept = [w for w in words if w.lower().strip(".,") not in _NAME_NOISE]
    # Una sola palabra generica ("Apple", "Target") es ambigua: solo vale el
    # nombre completo de dos o mas palabras, o los alias verificados.
    return " ".join(kept) if len(kept) >= 2 else None


def company_mentioned(company, text: str, evidence_level) -> bool:
    """True si el texto cita a la empresa: ticker con evidencia, alias verificado
    o nombre completo (>= 2 palabras distintivas). Sin inferir nada mas."""
    if evidence_level(company.ticker, company.name, text) > 0:
        return True
    terms = list(VERIFIED_ALIASES.get(company.ticker.upper(), ()))
    phrase = _name_phrase(getattr(company, "name", None))
    if phrase:
        terms.append(phrase)
    return any(
        re.search(rf"(?<![\w]){re.escape(term)}(?![\w])", text, flags=re.IGNORECASE)
        for term in terms
    )


def label_google(result: ConnectorResult, company, evidence_level) -> ConnectorResult:
    """Fuente = medio real (sufijo ' - Medio' del titular) y filtro de evidencia."""
    kept: list[ConnectorItem] = []
    for item in result.items:
        text = f"{item.title} {item.summary}"
        if not company_mentioned(company, text, evidence_level):
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


class Deadline:
    """Presupuesto de tiempo de un barrido, con reloj inyectable para tests.

    El actor lo consulta antes de cada unidad (empresa o feed) y el resultado
    nunca debe marcarse "ok" si el barrido se corto: el coalescer solo conserva
    la marca de frescura con status "ok" y un barrido truncado debe reintentarse
    en el siguiente tick.
    """

    def __init__(self, seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._end = clock() + seconds
        self.truncated = False

    def expired(self) -> bool:
        if self._clock() > self._end:
            self.truncated = True
        return self.truncated


def finalize_status(base_status: str, truncated: bool) -> str:
    """Un barrido cortado por tiempo es "partial", salvo que ya fuese "error"."""
    if truncated and base_status == "ok":
        return "partial"
    return base_status
