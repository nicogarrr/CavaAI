from __future__ import annotations

import asyncio
import threading
import time
from datetime import UTC, datetime

import httpx

from app.services.connectors.base import ConnectorItem, ConnectorResult


class GDELTClient:
    """Cliente GDELT DOC 2.0 con pacing global y respeto a 429.

    GDELT (tier gratuito) pide ~1 petición cada 5 segundos. Sin pacing, un
    ciclo de ``refresh_news`` sobre todas las compañías y tenants provoca una
    tormenta de 429 que satura la cola dramatiq. El pacing es a nivel de
    clase (proceso): todas las instancias comparten la misma ventana.

    429: se honra ``Retry-After`` (acotado) hasta ``max_429_retries`` veces;
    después se deja subir el error y el conector degrada a ``failed``.
    """

    base_url = "https://api.gdeltproject.org/api/v2/doc/doc"

    _rate_lock = threading.Lock()
    _next_allowed_at = 0.0  # time.monotonic()

    DEFAULT_MIN_INTERVAL = 5.0
    DEFAULT_MAX_429_RETRIES = 2
    MAX_RETRY_AFTER = 120.0
    DEFAULT_RETRY_AFTER = 30.0

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        min_interval: float | None = None,
        max_429_retries: int | None = None,
    ) -> None:
        self.client = client
        self.min_interval = (
            self.DEFAULT_MIN_INTERVAL if min_interval is None else min_interval
        )
        self.max_429_retries = (
            self.DEFAULT_MAX_429_RETRIES
            if max_429_retries is None
            else max_429_retries
        )

    async def _throttle(self) -> None:
        with GDELTClient._rate_lock:
            now = time.monotonic()
            start = max(now, GDELTClient._next_allowed_at)
            GDELTClient._next_allowed_at = start + self.min_interval
            delay = start - now
        if delay > 0:
            await asyncio.sleep(delay)

    @classmethod
    def _retry_after_seconds(cls, response: httpx.Response) -> float:
        raw = response.headers.get("Retry-After")
        if raw:
            try:
                return min(float(raw), cls.MAX_RETRY_AFTER)
            except ValueError:
                pass
        return cls.DEFAULT_RETRY_AFTER

    async def news_search(self, query: str, max_records: int = 50) -> dict:
        params = {
            "query": query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": max_records,
            "sort": "hybridrel",
        }
        attempt = 0
        while True:
            await self._throttle()
            if self.client is not None:
                response = await self.client.get(self.base_url, params=params)
            else:
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.get(self.base_url, params=params)
            if response.status_code == 429 and attempt < self.max_429_retries:
                attempt += 1
                await asyncio.sleep(self._retry_after_seconds(response))
                continue
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
