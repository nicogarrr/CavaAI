from typing import Any, Literal, Protocol

import httpx
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models import CustomMetricDefinition, SavedScreen
from app.services.screener_service import CustomMetricService, ScreenerService


router = APIRouter()


class CustomMetricCreate(BaseModel):
    metric_key: str = Field(min_length=2, max_length=160)
    name: str = Field(min_length=1, max_length=240)
    formula: str = Field(min_length=1, max_length=1000)
    unit: str = Field(default="decimal", min_length=1, max_length=40)
    description: str = Field(default="", max_length=5000)


class Criterion(BaseModel):
    left: str = Field(min_length=1, max_length=1000)
    operator: Literal[">", ">=", "<", "<=", "==", "!="]
    right: str = Field(min_length=1, max_length=1000)


class ScreenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=5000)
    criteria: list[Criterion] = Field(min_length=1, max_length=30)
    ranking_formula: str | None = Field(default=None, max_length=1000)
    ranking_direction: Literal["asc", "desc"] = "desc"
    alerts_enabled: bool = True


class AdHocScreen(BaseModel):
    criteria: list[Criterion] = Field(min_length=1, max_length=30)
    ranking_formula: str | None = Field(default=None, max_length=1000)
    ranking_direction: Literal["asc", "desc"] = "desc"


def _metric_payload(row: CustomMetricDefinition) -> dict[str, Any]:
    return {
        "id": row.id,
        "metric_key": row.metric_key,
        "name": row.name,
        "formula": row.formula,
        "unit": row.unit,
        "description": row.description,
        "version": row.version,
        "active": row.active,
        "metadata": row.metadata_,
        "created_at": row.created_at,
    }


def _screen_payload(row: SavedScreen) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "criteria": row.criteria,
        "ranking_formula": row.ranking_formula,
        "ranking_direction": row.ranking_direction,
        "alerts_enabled": row.alerts_enabled,
        "active": row.active,
        "last_run_at": row.last_run_at,
        "created_at": row.created_at,
    }


@router.get("/custom-metrics")
def list_custom_metrics(db: Session = Depends(get_db)) -> list[dict]:
    return [_metric_payload(row) for row in CustomMetricService.active(db)]


@router.post("/custom-metrics", status_code=201)
def create_custom_metric(
    payload: CustomMetricCreate, db: Session = Depends(get_db)
) -> dict:
    try:
        row = CustomMetricService().create(db, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _metric_payload(row)


@router.get("/screens")
def list_screens(db: Session = Depends(get_db)) -> list[dict]:
    return [
        _screen_payload(row)
        for row in db.scalars(select(SavedScreen).order_by(SavedScreen.name)).all()
    ]


@router.post("/screens", status_code=201)
def create_screen(payload: ScreenCreate, db: Session = Depends(get_db)) -> dict:
    try:
        row = ScreenerService().create_screen(
            db,
            name=payload.name,
            description=payload.description,
            criteria=[item.model_dump() for item in payload.criteria],
            ranking_formula=payload.ranking_formula,
            ranking_direction=payload.ranking_direction,
            alerts_enabled=payload.alerts_enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _screen_payload(row)


@router.post("/screens/{screen_id}/run")
def run_saved_screen(screen_id: int, db: Session = Depends(get_db)) -> dict:
    screen = db.get(SavedScreen, screen_id)
    if screen is None:
        raise HTTPException(status_code=404, detail="Saved screen not found")
    return ScreenerService().run_saved(db, screen)


@router.post("/run")
def run_ad_hoc_screen(payload: AdHocScreen, db: Session = Depends(get_db)) -> dict:
    try:
        return ScreenerService().run(
            db,
            criteria=[item.model_dump() for item in payload.criteria],
            ranking_formula=payload.ranking_formula,
            ranking_direction=payload.ranking_direction,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ============================================================================
# REAL-TIME SCREENER  —  GET /api/screeners/real
# ----------------------------------------------------------------------------
# Fuente elegida por defecto: Finnhub (free tier) — /quote da el precio real
# del día (c, d, dp, pc, v) y /stock/profile2 el nombre, market cap y sector
# reales. Yahoo Finance chart API es el vendor alternativo (gratuito, sin key;
# solo quotes, sin profile): se elige con SCREENER_QUOTE_VENDOR=yahoo.
# La fuente de quotes/profile es intercambiable vía SCREEN_VENDORS
# (protocolo ScreenQuoteVendor); el default Finnhub preserva el
# comportamiento actual.
# Yahoo público fue descartado tras probarlo en vivo: el screener
# (/v1/finance/screener/predefined) devuelve HTML bloqueado y /v7/finance/quote
# responde "Unauthorized" (requiere crumb). /stock/screener de Finnhub responde
# 404 sin plan premium.
#
# DISEÑO (screener mínimo HONESTO): universo fijo de ~35 grandes caps líquidos
# (la tabla companies contiene entradas de prueba tipo MATBIG/TPEER1 y small
# caps, así que el universo curado es la fuente primaria; la BD solo se usa
# para enriquecer nombre/sector cuando coincide). Cada ticker se consulta con
# precios y market cap REALES de Finnhub; los filtros marketCapMoreThan/sector
# se aplican sobre esos datos reales. Nunca se inventan precios.
#
# Cache (como market.py): resultado agregado 60s; perfil (nombre/mktcap/sector)
# 6h para no golpear el límite gratuito de 60 llamadas/min (refresco sostenido
# = ~35 /quote por minuto).
# ============================================================================

# (symbol, nombre de respaldo, sector de respaldo)
_REAL_UNIVERSE: list[tuple[str, str, str]] = [
    ("AAPL", "Apple", "Technology"),
    ("MSFT", "Microsoft", "Technology"),
    ("GOOGL", "Alphabet", "Communication Services"),
    ("AMZN", "Amazon", "Consumer Discretionary"),
    ("NVDA", "NVIDIA", "Technology"),
    ("TSLA", "Tesla", "Consumer Discretionary"),
    ("META", "Meta Platforms", "Communication Services"),
    ("BRK.B", "Berkshire Hathaway", "Financials"),
    ("JPM", "JPMorgan Chase", "Financials"),
    ("V", "Visa", "Financials"),
    ("UNH", "UnitedHealth", "Health Care"),
    ("WMT", "Walmart", "Consumer Staples"),
    ("PG", "Procter & Gamble", "Consumer Staples"),
    ("MA", "Mastercard", "Financials"),
    ("HD", "Home Depot", "Consumer Discretionary"),
    ("DIS", "Disney", "Communication Services"),
    ("NFLX", "Netflix", "Communication Services"),
    ("ADBE", "Adobe", "Technology"),
    ("CRM", "Salesforce", "Technology"),
    ("CSCO", "Cisco", "Technology"),
    ("PFE", "Pfizer", "Health Care"),
    ("INTC", "Intel", "Technology"),
    ("KO", "Coca-Cola", "Consumer Staples"),
    ("PEP", "PepsiCo", "Consumer Staples"),
    ("MRK", "Merck", "Health Care"),
    ("ABT", "Abbott", "Health Care"),
    ("BAC", "Bank of America", "Financials"),
    ("AMD", "Advanced Micro Devices", "Technology"),
    ("ORCL", "Oracle", "Technology"),
    ("AVGO", "Broadcom", "Technology"),
    ("XOM", "Exxon Mobil", "Energy"),
    ("CVX", "Chevron", "Energy"),
    ("JNJ", "Johnson & Johnson", "Health Care"),
    ("COST", "Costco", "Consumer Staples"),
    ("LIN", "Linde", "Materials"),
]

_ETF_SYMBOLS = {"SPY", "QQQ", "IWM", "DIA", "VOO", "VTI", "GLD"}

_FINNHUB_BASE = "https://finnhub.io/api/v1"
_PROFILE_TTL = 6 * 3600.0  # 6h: nombre/market cap/sector cambian lento
_QUOTE_TTL = 60.0  # precio real del día, refrescado cada minuto (como market.py)

# symbol -> {"at": monotonic, "data": {...}}
_real_profile_cache: dict[str, dict] = {}
_real_quote_cache: dict[str, dict] = {}
# Items crudos (todo el universo, sin filtrar) — los filtros se aplican por
# request sobre los datos cacheados, así cada combinación de filtros funciona
# sin golpear Finnhub de nuevo.
_real_items_cache: dict = {"at": 0.0, "items": []}


def _cs(_str: str | None) -> str:
    return (_str or "").strip().lower()


def _load_universe_from_db() -> dict[str, tuple[str, str]]:
    """Enriquecimiento best-effort desde companies (nombre/sector reales)."""
    try:
        from sqlalchemy import text as _text

        from app.core.database import SessionLocal

        with SessionLocal() as db:
            rows = db.execute(
                _text("SELECT ticker, name, sector FROM companies")
            ).fetchall()
        return {str(r[0]).upper(): (str(r[1]), str(r[2])) for r in rows}
    except Exception:  # noqa: BLE001 — el screener funciona sin BD
        return {}


class ScreenQuoteVendor(Protocol):
    """Fuente intercambiable de quotes/profile para el screener (Finnhub ↔ Yahoo).

    Cada vendor normaliza al mismo dict de quote
    (price/change/changePercent/volume/prevClose/asOf) y de profile
    (name/marketCap/sector/exchange). El default es Finnhub (comportamiento
    actual); Yahoo es la alternativa gratuita sin key.
    """

    name: str
    source_label: str

    def fetch_quote(self, client: httpx.Client, symbol: str) -> dict | None: ...
    def fetch_profile(self, client: httpx.Client, symbol: str) -> dict | None: ...


def _finnhub_get(
    client: httpx.Client, path: str, symbol: str, timeout: float
) -> dict | None:
    try:
        resp = client.get(
            f"{_FINNHUB_BASE}{path}",
            params={"symbol": symbol},
            timeout=timeout,
        )
        if resp.status_code == 429:  # rate limit free tier: saltar, cache sigue valiendo
            return None
        if resp.status_code != 200:
            return None
        payload = resp.json()
        return payload if isinstance(payload, dict) else None
    except (httpx.HTTPError, ValueError):
        return None


class FinnhubScreenVendor:
    """Vendor por defecto: Finnhub free tier (comportamiento actual)."""

    name = "finnhub"
    source_label = "finnhub_free"

    def fetch_quote(self, client: httpx.Client, symbol: str) -> dict | None:
        """Precio real del día vía Finnhub /quote (plan gratuito).

        Retry único en 429 (límite 60 llamadas/minuto): un fallo puntual no debe
        dejar el ticker fuera del screener.
        """
        raw = _finnhub_get(client, "/quote", symbol, timeout=8)
        if raw is None:  # posible 429: reintentar una vez tras 1s
            time.sleep(1.0)
            raw = _finnhub_get(client, "/quote", symbol, timeout=8)
        if raw and raw.get("c") and raw["c"] > 0:
            return {
                "price": float(raw["c"]),
                "change": float(raw.get("d") or 0.0),
                "changePercent": float(raw.get("dp") or 0.0),
                "volume": float(raw.get("v") or 0.0),
                "prevClose": float(raw.get("pc") or 0.0),
                "asOf": raw.get("t"),
            }
        return None

    def fetch_profile(self, client: httpx.Client, symbol: str) -> dict | None:
        """Perfil real (nombre, market cap en USD, sector, exchange) vía profile2."""
        raw = _finnhub_get(client, "/stock/profile2", symbol, timeout=8)
        if raw and raw.get("ticker"):
            return {
                "name": raw.get("name") or symbol,
                "marketCap": float(raw.get("marketCapitalization") or 0.0) * 1_000_000.0,
                "sector": raw.get("finnhubIndustry") or None,
                "exchange": raw.get("exchange") or "US",
            }
        return None


_YAHOO_CHART_BASE = "https://query1.finance.yahoo.com/v8/finance/chart"
_YAHOO_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


class YahooScreenVendor:
    """Vendor alternativo: Yahoo Finance chart API (gratuita, sin key).

    Normaliza al mismo formato que Finnhub. Sin profile real (el endpoint
    /v7/finance/quote de Yahoo requiere crumb y devuelve "Unauthorized"):
    fetch_profile devuelve None y el nombre/sector caen al universo/DB.
    """

    name = "yahoo"
    source_label = "yahoo_finance"

    def fetch_quote(self, client: httpx.Client, symbol: str) -> dict | None:
        try:
            resp = client.get(
                f"{_YAHOO_CHART_BASE}/{symbol}",
                params={"range": "5d", "interval": "1d"},
                headers=_YAHOO_HEADERS,
                timeout=15,
            )
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None
        try:
            payload = resp.json()
            result = payload["chart"]["result"][0]
            closes = [
                value
                for value in result["indicators"]["quote"][0]["close"]
                if value is not None
            ]
            if not closes or closes[-1] <= 0:
                return None
            volumes = [
                value
                for value in result["indicators"]["quote"][0].get("volume") or []
                if value is not None
            ]
            timestamps = result.get("timestamp") or []
            meta = result.get("meta") or {}
            last, previous = closes[-1], (
                closes[-2] if len(closes) >= 2
                else meta.get("chartPreviousClose") or closes[-1]
            )
            change = last - previous
            return {
                "price": float(last),
                "change": float(change),
                "changePercent": float(change / previous * 100) if previous else 0.0,
                "volume": float(volumes[-1]) if volumes else 0.0,
                "prevClose": float(previous),
                "asOf": timestamps[-1] if timestamps else None,
            }
        except (KeyError, IndexError, TypeError, ValueError):
            return None

    def fetch_profile(self, client: httpx.Client, symbol: str) -> dict | None:
        return None


SCREEN_VENDORS: dict[str, ScreenQuoteVendor] = {
    FinnhubScreenVendor.name: FinnhubScreenVendor(),
    YahooScreenVendor.name: YahooScreenVendor(),
}
DEFAULT_SCREENER_VENDOR = "finnhub"


def resolve_screener_vendor(name: str | None) -> ScreenQuoteVendor:
    """Devuelve el vendor pedido o el default (Finnhub) si es desconocido/vacío."""
    if not name:
        return SCREEN_VENDORS[DEFAULT_SCREENER_VENDOR]
    return SCREEN_VENDORS.get(
        name.strip().lower(), SCREEN_VENDORS[DEFAULT_SCREENER_VENDOR]
    )


def _fetch_quote(
    client: httpx.Client, symbol: str, *, vendor: str | None = None
) -> dict | None:
    now = time.monotonic()
    active = resolve_screener_vendor(vendor)
    cache_key = f"{active.name}:{symbol}"
    cached = _real_quote_cache.get(cache_key)
    if cached and now - cached["at"] < _QUOTE_TTL:
        return cached["data"]
    data = active.fetch_quote(client, symbol)
    if data:
        _real_quote_cache[cache_key] = {"at": now, "data": data}
    return data


def _fetch_profile(
    client: httpx.Client, symbol: str, *, vendor: str | None = None
) -> dict | None:
    now = time.monotonic()
    active = resolve_screener_vendor(vendor)
    cache_key = f"{active.name}:{symbol}"
    cached = _real_profile_cache.get(cache_key)
    if cached and now - cached["at"] < _PROFILE_TTL:
        return cached["data"]
    data = active.fetch_profile(client, symbol)
    if data:
        _real_profile_cache[cache_key] = {"at": now, "data": data}
    return data


@router.get("/real")
def real_time_screener(
    marketCapMoreThan: float | None = None,
    sector: str | None = None,
    limit: int = 25,
) -> dict:
    """Screener real: precios del día + market cap reales (Finnhub free).

    marketCapMoreThan: mínimo de market cap en USD (real de Finnhub).
    sector: filtro case-insensitive sobre el sector (BD/Finnhub).
    Vendor de quotes/profile (Finnhub ↔ Yahoo) configurable vía
    SCREENER_QUOTE_VENDOR; default Finnhub.
    """
    settings = get_settings()
    vendor = resolve_screener_vendor(settings.screener_quote_vendor)
    now = time.monotonic()
    # Refresco solo si caduca el cache de 60s; los filtros se aplican abajo
    # sobre los items crudos, así cada combinación es correcta sin re-consultar.
    if (
        now - _real_items_cache["at"] >= _QUOTE_TTL
        or not _real_items_cache["items"]
    ):
        items = _refetch_real_items(vendor=vendor.name)
        if items:  # last-known-good si el refresco falla del todo
            _real_items_cache["at"] = now
            _real_items_cache["items"] = items

    filtered = [
        item
        for item in _real_items_cache["items"]
        if (
            marketCapMoreThan is None
            or (item["marketCap"] or 0.0) >= marketCapMoreThan
        )
        and (not sector or _cs(item["sector"]) == _cs(sector))
    ]
    filtered.sort(key=lambda item: (item["marketCap"] or 0.0), reverse=True)
    limited = filtered[: max(1, min(limit, 200))]
    return {
        "source": vendor.source_label,
        "as_of": time.time(),
        "count": len(limited),
        "screener": limited,
    }


def _refetch_real_items(*, vendor: str | None = None) -> list[dict]:
    """Universo completo con precios/market cap reales (vendor configurable).

    Fase 1: /quote en paralelo (35 llamadas, con retry en 429).
    Fase 2: /stock/profile2 solo si el cache (6h) está vacío/caducado, con
    pacing de 0.3s entre llamadas para respetar las 60 llamadas/minuto del
    plan gratuito (a partir del segundo refresco los profiles vienen de cache
    y solo se hacen ~35 /quote por minuto).
    """
    db_universe = _load_universe_from_db()
    settings = get_settings()
    active = resolve_screener_vendor(
        vendor if vendor is not None else settings.screener_quote_vendor
    )
    headers = {"User-Agent": "CavaAI/0.1"}

    quotes: dict[str, dict] = {}
    with httpx.Client(headers=headers, timeout=15) as client:
        fn_key = settings.finnhub_api_key
        client.params = {"token": fn_key} if fn_key and active.name == "finnhub" else {}
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {
                pool.submit(_fetch_quote, client, symbol, vendor=active.name): symbol
                for symbol, _, _ in _REAL_UNIVERSE
            }
            for future in futures:
                symbol = futures[future]
                quote = future.result()
                if quote:
                    quotes[symbol] = quote

    profiles: dict[str, dict] = {}
    with httpx.Client(headers=headers, timeout=15) as client:
        fn_key = settings.finnhub_api_key
        client.params = {"token": fn_key} if fn_key and active.name == "finnhub" else {}
        for symbol, _, _ in _REAL_UNIVERSE:
            if symbol not in quotes:
                continue
            if time.monotonic() - _real_profile_cache.get(
                f"{active.name}:{symbol}", {}
            ).get("at", 0.0) < _PROFILE_TTL:
                profiles[symbol] = _real_profile_cache[f"{active.name}:{symbol}"]["data"]
                continue
            profile = _fetch_profile(client, symbol, vendor=active.name)
            if profile:
                profiles[symbol] = profile
            time.sleep(0.3)  # pacing: ~3.3 llamadas/s, muy por debajo de 60/min

    items: list[dict] = []
    for symbol, name_fb, sector_fb in _REAL_UNIVERSE:
        quote = quotes.get(symbol)
        if not quote:
            continue
        profile = profiles.get(symbol)
        db_row = db_universe.get(symbol)
        name = (db_row[0] if db_row else None) or (
            profile["name"] if profile else name_fb
        )
        sector_value = (
            db_row[1]
            if db_row
            else (profile["sector"] if profile and profile["sector"] else sector_fb)
        )
        items.append(
            {
                "symbol": symbol,
                "name": name,
                "price": quote["price"],
                "change": quote["change"],
                "changePercent": quote["changePercent"],
                "marketCap": profile["marketCap"] if profile else 0.0,
                "volume": quote["volume"],
                "prevClose": quote["prevClose"],
                "sector": sector_value,
                "exchange": profile["exchange"] if profile else "US",
                "type": "ETF" if symbol.upper() in _ETF_SYMBOLS else "Stock",
                "pe": None,
                "pb": None,
                "roe": None,
                "beta": None,
            }
        )
    return items
