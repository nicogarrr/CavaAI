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
