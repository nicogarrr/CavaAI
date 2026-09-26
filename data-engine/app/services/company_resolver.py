"""Resolución de compañías por ticker con fallback de sufijo de mercado.

La píldora de búsqueda navega a /research/<displaySymbol> (SAN.MC, IBE.MC,
AIR.PA...) mientras el universo de research usa el ticker base (SAN, IBE,
AIR). Sin fallback, todas las rutas /api/companies/{ticker} devolvían 404
para acciones europeas llegando desde el buscador.

Reglas:
- El match exacto siempre gana (BRK.B, BF.A y tickers reales con punto
  nunca se tocan).
- El fallback solo aplica cuando el exacto falla y el sufijo es un mercado
  conocido (mismo mapa que el frontend usa para etiquetar la bolsa).
- Nunca crea ni inventa compañías: miss -> None, y el caller decide (404).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company

KNOWN_MARKET_SUFFIXES = frozenset({
    "MC",  # Bolsa de Madrid
    "L",   # London
    "PA",  # Euronext Paris
    "AS",  # Euronext Amsterdam
    "BR",  # Euronext Brussels
    "LS",  # Euronext Lisbon
    "DE",  # XETRA
    "F",   # Frankfurt
    "MI",  # Borsa Italiana
    "SW",  # SIX
    "VI",  # Wiener Börse
    "HE",  # Nasdaq Helsinki
    "ST",  # Nasdaq Stockholm
    "CO",  # Nasdaq Copenhagen
    "OL",  # Oslo Børs
    "HK",  # HKEX
    "T",   # Tokyo
    "AX",  # ASX
    "TO",  # TSX
    "V",   # TSXV
    "MX",  # BMV
    "SA",  # B3
})


def resolve_company(db: Session, ticker: str) -> Company | None:
    """Devuelve la Company por ticker exacto o, si falla y hay sufijo de
    mercado conocido, por ticker base. None si no existe."""
    normalized = ticker.strip().upper()
    company = db.scalar(select(Company).where(Company.ticker == normalized))
    if company is not None:
        return company
    if "." not in normalized:
        return None
    base, _, suffix = normalized.rpartition(".")
    if not base or suffix not in KNOWN_MARKET_SUFFIXES:
        return None
    return db.scalar(select(Company).where(Company.ticker == base))


def resolve_companies(
    db: Session, tickers: list[str]
) -> tuple[list[Company], list[str]]:
    """Resuelve N tickers con la politica de ``resolve_company`` en 1-2 queries.

    Misma politica: el match exacto siempre gana (BRK.B, BF.A y tickers
    reales con punto nunca se tocan) y el fallback a ticker base solo
    aplica con sufijo de mercado conocido. Un IN para los exactos y, solo
    si hay alias pendientes, un segundo IN para sus bases. Devuelve las
    Company en el orden pedido (deduplicadas por id) y los tickers sin
    match, en orden. Nunca crea ni inventa compañías.
    """
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in tickers:
        ticker = raw.strip().upper()
        if ticker and ticker not in seen:
            seen.add(ticker)
            normalized.append(ticker)
    if not normalized:
        return [], []
    exact = {
        company.ticker: company
        for company in db.scalars(
            select(Company).where(Company.ticker.in_(normalized))
        ).all()
    }
    alias_bases = {}  # ticker pedido -> ticker base candidato
    for ticker in normalized:
        if ticker in exact or "." not in ticker:
            continue
        base, _, suffix = ticker.rpartition(".")
        if base and suffix in KNOWN_MARKET_SUFFIXES:
            alias_bases[ticker] = base
    bases = {}
    if alias_bases:
        bases = {
            company.ticker: company
            for company in db.scalars(
                select(Company).where(
                    Company.ticker.in_(sorted(set(alias_bases.values())))
                )
            ).all()
        }
    companies: list[Company] = []
    resolved_ids: set[int] = set()
    missing: list[str] = []
    for ticker in normalized:
        company = exact.get(ticker) or bases.get(alias_bases.get(ticker, ""))
        if company is None:
            missing.append(ticker)
        elif company.id not in resolved_ids:
            resolved_ids.add(company.id)
            companies.append(company)
    return companies, missing
