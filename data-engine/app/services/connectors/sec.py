import httpx

from app.core.config import get_settings


class SECClient:
    submissions_url = "https://data.sec.gov/submissions"
    companyfacts_url = "https://data.sec.gov/api/xbrl/companyfacts"
    ticker_map_url = "https://www.sec.gov/files/company_tickers.json"

    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def headers(self) -> dict:
        return {"User-Agent": self.settings.sec_user_agent, "Accept-Encoding": "gzip, deflate"}

    async def ticker_map(self) -> dict:
        async with httpx.AsyncClient(timeout=30, headers=self.headers) as client:
            response = await client.get(self.ticker_map_url)
            response.raise_for_status()
            return response.json()

    async def cik_for_ticker(self, ticker: str) -> str | None:
        ticker = ticker.upper()
        mapping = await self.ticker_map()
        for item in mapping.values():
            if item.get("ticker", "").upper() == ticker:
                return str(item["cik_str"]).zfill(10)
        return None

    async def submissions(self, cik: str) -> dict:
        padded = str(cik).zfill(10)
        async with httpx.AsyncClient(timeout=30, headers=self.headers) as client:
            response = await client.get(f"{self.submissions_url}/CIK{padded}.json")
            response.raise_for_status()
            return response.json()

    async def company_facts(self, cik: str) -> dict:
        padded = str(cik).zfill(10)
        async with httpx.AsyncClient(timeout=30, headers=self.headers) as client:
            response = await client.get(f"{self.companyfacts_url}/CIK{padded}.json")
            response.raise_for_status()
            return response.json()

