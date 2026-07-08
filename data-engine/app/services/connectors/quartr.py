import httpx

from app.core.config import get_settings


class QuartrClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def configured(self) -> bool:
        return bool(self.settings.quartr_api_key)

    @property
    def headers(self) -> dict:
        if not self.settings.quartr_api_key:
            raise RuntimeError("QUARTR_API_KEY is not configured")
        return {"Authorization": f"Bearer {self.settings.quartr_api_key}"}

    async def get(self, path: str, params: dict | None = None) -> dict | list:
        if not self.configured():
            raise RuntimeError("QUARTR_API_KEY is not configured")
        url = f"{self.settings.quartr_api_base_url.rstrip('/')}/{path.lstrip('/')}"
        async with httpx.AsyncClient(timeout=30, headers=self.headers) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()

