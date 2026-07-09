from __future__ import annotations

from datetime import UTC, datetime

import httpx

from app.services.connectors.base import ConnectorItem, ConnectorResult


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


def _gdelt_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    for date_format in ("%Y%m%dT%H%M%SZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(value, date_format).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


class GDELTConnector:
    """Normalize the existing GDELT client into the connector result contract."""

    def __init__(self, client: GDELTClient | None = None) -> None:
        self.client = client or GDELTClient()

    async def poll(
        self,
        query: str,
        *,
        ticker: str | None = None,
        max_records: int = 50,
    ) -> ConnectorResult:
        metadata = {"query": query, "ticker": ticker, "max_records": max_records}
        try:
            payload = await self.client.news_search(query, max_records=max_records)
            articles = payload.get("articles", []) if isinstance(payload, dict) else []
            items: list[ConnectorItem] = []
            seen: set[str] = set()
            for article in articles:
                if not isinstance(article, dict):
                    continue
                url = article.get("url")
                title = " ".join(str(article.get("title") or "").split())
                key = url or title
                if not key or key in seen:
                    continue
                seen.add(key)
                items.append(
                    ConnectorItem(
                        source=str(article.get("domain") or "GDELT"),
                        title=title or "Untitled GDELT article",
                        url=url,
                        summary=" ".join(str(article.get("snippet") or "").split()),
                        published_at=_gdelt_datetime(article.get("seendate")),
                        ticker=ticker.upper() if ticker else None,
                        item_type="news",
                        external_id=url,
                        metadata={
                            "language": article.get("language"),
                            "source_country": article.get("sourcecountry"),
                            "social_image": article.get("socialimage"),
                        },
                    )
                )
            metadata["article_count"] = len(articles)
            return ConnectorResult(source="gdelt", items=items, metadata=metadata)
        except Exception as exc:
            return ConnectorResult.failed("gdelt", exc, metadata=metadata)

