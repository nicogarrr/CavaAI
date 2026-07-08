import httpx


class GDELTClient:
    base_url = "https://api.gdeltproject.org/api/v2/doc/doc"

    async def news_search(self, query: str, max_records: int = 50) -> dict:
        params = {
            "query": query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": max_records,
            "sort": "hybridrel",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(self.base_url, params=params)
            response.raise_for_status()
            return response.json()

