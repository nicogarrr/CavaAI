import httpx

from app.core.config import get_settings


class FMPClient:
    """FMP connector.

    FMP retired the legacy /api/v3 endpoints for current API keys (they return
    403 "Legacy Endpoint no longer supported"), so every method targets the
    /stable API with ?symbol= query parameters. Provider/entitlement errors
    (e.g. 402 on endpoints outside the current plan) surface as exceptions so
    callers mark coverage unavailable instead of fabricating data.
    """

    base_url = "https://financialmodelingprep.com/stable"

    def __init__(self) -> None:
        self.settings = get_settings()

    def configured(self) -> bool:
        return bool(self.settings.fmp_api_key)

    async def _get(self, path: str, params: dict | None = None) -> list | dict:
        if not self.configured():
            raise RuntimeError("FMP_API_KEY is not configured")
        merged = {**(params or {}), "apikey": self.settings.fmp_api_key}
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{self.base_url}{path}", params=merged)
            response.raise_for_status()
            return response.json()

    async def company_profile(self, ticker: str) -> list | dict:
        return await self._get("/profile", {"symbol": ticker.upper()})

    async def dividends(self, ticker: str) -> list | dict:
        """Declared dividend records for a symbol (FMP stable/dividends).

        Returns the raw provider payload. Entitlement/auth errors surface as
        exceptions so callers can mark coverage unavailable instead of
        fabricating dividend data.
        """
        return await self._get("/dividends", {"symbol": ticker.upper()})

    async def splits(self, ticker: str) -> list | dict:
        """Historical stock splits for a symbol (FMP stable/splits).

        Errors surface as exceptions so callers mark coverage unavailable
        instead of guessing share-count adjustments.
        """
        return await self._get("/splits", {"symbol": ticker.upper()})

    async def income_statement(self, ticker: str, limit: int = 10) -> list | dict:
        return await self._get("/income-statement", {"symbol": ticker.upper(), "limit": limit})

    async def balance_sheet(self, ticker: str, limit: int = 10) -> list | dict:
        return await self._get("/balance-sheet-statement", {"symbol": ticker.upper(), "limit": limit})

    async def cash_flow(self, ticker: str, limit: int = 10) -> list | dict:
        return await self._get("/cash-flow-statement", {"symbol": ticker.upper(), "limit": limit})

    async def ratios(self, ticker: str, limit: int = 10) -> list | dict:
        return await self._get("/ratios", {"symbol": ticker.upper(), "limit": limit})

    async def news(self, ticker: str, limit: int = 25) -> list | dict:
        """Latest stock news for a symbol (FMP stable/news/stock).

        FMP plans without news coverage answer 402 here; the error propagates
        so callers mark news coverage unavailable rather than showing stale or
        invented headlines.
        """
        return await self._get("/news/stock", {"symbols": ticker.upper(), "limit": limit})
