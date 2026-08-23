"""Enrich Company master data from market-data APIs (Finnhub).

The company catalogue is a bootstrap seed, NOT the source of truth for
display names. When a Company's name is a placeholder (equals its ticker,
contains underscores, or is missing) or its exchange is unknown, we ask a
market-data API (Finnhub /stock/profile2) for the real name and metadata.
"""
from __future__ import annotations

import logging
import time

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Company

logger = logging.getLogger(__name__)

_PLACEHOLDER_EXCHANGES = {None, "", "UNKNOWN", "UNKNOWN_EXCHANGE"}


class CompanyEnrichmentService:
    """Completa Company.name/exchange/sector/currency desde Finnhub."""

    def __init__(self, settings=None, client: httpx.Client | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = client or httpx.Client(timeout=15)

    def close(self) -> None:
        self._client.close()

    # -- consulta a la API -------------------------------------------------
    def _finnhub_profile(self, ticker: str) -> dict | None:
        key = self.settings.finnhub_api_key
        if not key:
            logger.info("FINNHUB_API_KEY no configurada; sin enriquecimiento")
            return None
        try:
            resp = self._client.get(
                "https://finnhub.io/api/v1/stock/profile2",
                params={"symbol": ticker, "token": key},
            )
            if resp.status_code == 200:
                data = resp.json()
                if data and data.get("name"):
                    return data
        except httpx.HTTPError as exc:
            logger.warning("Finnhub profile2 fallo para %s: %s", ticker, exc)
        # Fallback: /search devuelve el nombre incluso para simbolos que
        # profile2 no cubre (p.ej. ADUR = Aduro Clean Technologies Inc).
        return self._finnhub_search(ticker)

    def _finnhub_search(self, ticker: str) -> dict | None:
        key = self.settings.finnhub_api_key
        if not key:
            return None
        try:
            resp = self._client.get(
                "https://finnhub.io/api/v1/search",
                params={"q": ticker, "token": key},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            for item in data.get("result", []):
                symbol = (item.get("symbol") or "").upper()
                if symbol == ticker.upper():
                    description = (item.get("description") or "").strip()
                    if description:
                        return {"name": description}
            return None
        except httpx.HTTPError as exc:
            logger.warning("Finnhub search fallo para %s: %s", ticker, exc)
        return None

    # -- criterio de enriquecimiento --------------------------------------
    @staticmethod
    def needs_enrichment(company: Company) -> bool:
        name = (company.name or "").strip()
        return (
            not name
            or name.upper() == (company.ticker or "").upper()
            or "_" in name
            or company.exchange in _PLACEHOLDER_EXCHANGES
        )

    # -- aplicacion ---------------------------------------------------------
    def enrich(self, db: Session, company: Company, persist: bool = True) -> bool:
        """Actualiza name/exchange/industry/currency si la API tiene datos mejores."""
        if not self.needs_enrichment(company):
            return False
        profile = self._finnhub_profile(company.ticker)
        if not profile:
            return False
        changed = False

        name = (profile.get("name") or "").strip()
        if name and name != company.name:
            company.name = name
            changed = True
        exchange = (profile.get("exchange") or "").strip()
        if exchange:
            company.exchange = exchange
            changed = True
        industry = (profile.get("finnhubIndustry") or "").strip()
        if industry and industry.upper() not in {"N/A", "UNKNOWN"}:
            company.industry = industry
            changed = True
        currency = (profile.get("currency") or "").strip()
        if currency:
            company.currency = currency
            changed = True

        if changed and persist:
            db.add(company)
        return changed

    def enrich_all(self, db: Session, sleep_between: float = 0.8) -> dict:
        """Barre companies con datos debiles y las enriquece (respetando rate limit)."""
        rows = list(db.scalars(select(Company).order_by(Company.ticker)).all())
        enriched, skipped, not_found = 0, 0, 0
        for company in rows:
            if not self.needs_enrichment(company):
                skipped += 1
                continue
            if self.enrich(db, company):
                enriched += 1
            else:
                not_found += 1
            time.sleep(sleep_between)
        if enriched:
            db.commit()
        return {
            "total": len(rows),
            "enriched": enriched,
            "already_ok": skipped,
            "api_sin_datos": not_found,
        }