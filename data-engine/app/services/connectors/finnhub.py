from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings


class FinnhubClient:
    base_url = "https://finnhub.io/api/v1"

    def __init__(self) -> None:
        self.settings = get_settings()

    def configured(self) -> bool:
        return bool(self.settings.finnhub_api_key)

    async def quote(self, ticker: str) -> dict[str, Any]:
        if not self.configured():
            raise RuntimeError("FINNHUB_API_KEY is not configured")
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{self.base_url}/quote",
                params={"symbol": ticker.upper(), "token": self.settings.finnhub_api_key},
            )
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Finnhub returned an invalid quote")
        return payload
