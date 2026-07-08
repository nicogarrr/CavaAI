import httpx

from app.core.config import get_settings


class FMPClient:
    base_url = "https://financialmodelingprep.com/api/v3"

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
        return await self._get(f"/profile/{ticker.upper()}")

    async def income_statement(self, ticker: str, limit: int = 10) -> list | dict:
        return await self._get(f"/income-statement/{ticker.upper()}", {"limit": limit})

    async def balance_sheet(self, ticker: str, limit: int = 10) -> list | dict:
        return await self._get(f"/balance-sheet-statement/{ticker.upper()}", {"limit": limit})

    async def cash_flow(self, ticker: str, limit: int = 10) -> list | dict:
        return await self._get(f"/cash-flow-statement/{ticker.upper()}", {"limit": limit})

    async def ratios(self, ticker: str, limit: int = 10) -> list | dict:
        return await self._get(f"/ratios/{ticker.upper()}", {"limit": limit})

    async def news(self, ticker: str, limit: int = 25) -> list | dict:
        return await self._get("/stock_news", {"tickers": ticker.upper(), "limit": limit})

