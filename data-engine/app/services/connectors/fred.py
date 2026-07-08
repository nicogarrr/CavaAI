import httpx

from app.core.config import get_settings


class FREDClient:
    base_url = "https://api.stlouisfed.org/fred"

    def __init__(self) -> None:
        self.settings = get_settings()

    def configured(self) -> bool:
        return bool(self.settings.fred_api_key)

    async def series(self, series_id: str, limit: int = 120) -> dict:
        if not self.configured():
            raise RuntimeError("FRED_API_KEY is not configured")
        params = {
            "series_id": series_id,
            "api_key": self.settings.fred_api_key,
            "file_type": "json",
            "limit": limit,
            "sort_order": "desc",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{self.base_url}/series/observations", params=params)
            response.raise_for_status()
            return response.json()

