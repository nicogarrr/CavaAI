from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import urlparse

import httpx

from app.services.connectors import (
    ConnectorResult,
    GDELTConnector,
    IRConnector,
    RSSConnector,
    SECClient,
)


@dataclass(frozen=True, slots=True)
class RSSFeed:
    url: str
    ticker: str | None = None


def configured_rss_feeds(value: str | None = None) -> list[RSSFeed]:
    """Parse RSS_FEEDS as JSON or comma/newline separated URL[|TICKER] values."""

    raw = value if value is not None else os.getenv("RSS_FEEDS", "")
    if not raw.strip():
        return []

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = None

    feeds: list[RSSFeed] = []
    if isinstance(payload, list):
        for entry in payload:
            if isinstance(entry, str):
                feeds.extend(configured_rss_feeds(entry))
            elif isinstance(entry, dict) and entry.get("url"):
                ticker = str(entry["ticker"]).upper() if entry.get("ticker") else None
                feeds.append(RSSFeed(url=str(entry["url"]), ticker=ticker))
        return _unique_feeds(feeds)

    for entry in raw.replace("\n", ",").split(","):
        entry = entry.strip()
        if not entry:
            continue
        first, separator, second = entry.partition("|")
        if separator and not first.lower().startswith(("http://", "https://")):
            ticker, url = first.upper(), second
        else:
            url, ticker = first, second.upper() if separator and second else None
        if url.lower().startswith(("http://", "https://")):
            feeds.append(RSSFeed(url=url, ticker=ticker or None))
    return _unique_feeds(feeds)


def _unique_feeds(feeds: list[RSSFeed]) -> list[RSSFeed]:
    unique: list[RSSFeed] = []
    seen: set[tuple[str, str | None]] = set()
    for feed in feeds:
        key = (feed.url, feed.ticker)
        if key not in seen:
            seen.add(key)
            unique.append(feed)
    return unique


class FeedIngestionService:
    """Poll connectors and adapt their common result into existing ingestion services."""

    def __init__(self, *, sec_client: SECClient | None = None) -> None:
        self._sec_client = sec_client

    async def poll_rss(
        self,
        url: str,
        *,
        ticker: str | None = None,
        max_items: int = 100,
        connector: RSSConnector | None = None,
    ) -> ConnectorResult:
        return await (connector or RSSConnector()).poll(
            url,
            ticker=ticker,
            max_items=max_items,
        )

    async def poll_gdelt(
        self,
        query: str,
        *,
        ticker: str | None = None,
        max_records: int = 50,
        connector: GDELTConnector | None = None,
    ) -> ConnectorResult:
        return await (connector or GDELTConnector()).poll(
            query,
            ticker=ticker,
            max_records=max_records,
        )

    async def poll_sec(
        self,
        cik: str,
        *,
        ticker: str | None = None,
        forms: set[str] | None = None,
        limit: int = 40,
        client: SECClient | None = None,
    ) -> ConnectorResult:
        sec = client or self._sec_client
        if sec is None:
            sec = SECClient()
            self._sec_client = sec
        return await sec.recent_filings(
            cik,
            forms=forms or {"10-K", "10-Q", "8-K", "20-F", "6-K"},
            limit=limit,
            ticker=ticker,
        )

    async def poll_ir(
        self,
        ir_url: str,
        *,
        ticker: str | None = None,
        max_items: int = 100,
        connector: IRConnector | None = None,
    ) -> ConnectorResult:
        return await (connector or IRConnector()).poll(
            ir_url,
            ticker=ticker,
            max_items=max_items,
        )

    def ingest_news_result(
        self,
        db,
        result: ConnectorResult,
        *,
        ticker: str | None = None,
    ) -> dict:
        """Ingest connector items without importing model-dependent services at startup."""

        if not result.items:
            return {
                "status": result.status,
                "source": result.source,
                "received": 0,
                "created": 0,
                "skipped_duplicates": 0,
                "requires_update": 0,
                "errors": list(result.errors),
            }

        from app.schemas import NewsFeedItem
        from app.services.news_service import NewsService

        news_items = [
            NewsFeedItem(
                title=item.title,
                text=item.summary or None,
                ticker=item.ticker or ticker,
                url=item.url,
                source=item.source or result.source,
                published_at=item.published_at,
            )
            for item in result.items
        ]
        response = NewsService().ingest_news_items(
            db,
            news_items,
            default_source=result.source,
        )
        payload = response.model_dump(mode="json")
        payload["source"] = result.source
        payload["connector_errors"] = list(result.errors)
        return payload

    async def ingest_document_url(
        self,
        db,
        *,
        ticker: str,
        title: str,
        url: str,
        source_type: str,
        published_at=None,
    ) -> dict:
        """Download a discovered document, preserving SEC request policy when needed."""

        parsed_url = urlparse(url)
        if parsed_url.scheme not in {"http", "https"}:
            raise ValueError("Only http(s) URLs can be ingested")

        if (parsed_url.hostname or "").lower() in {"sec.gov", "www.sec.gov"}:
            content, content_type = await SECClient().filing_document(url)
        else:
            async with httpx.AsyncClient(
                timeout=30,
                follow_redirects=True,
                headers={"User-Agent": "CavaAI Document Poller/1.0"},
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                content = response.content
                content_type = response.headers.get("content-type")

        from app.services.document_ingestion_service import DocumentIngestionService

        filename = PurePosixPath(parsed_url.path).name or f"{parsed_url.hostname}.html"
        return DocumentIngestionService().ingest_bytes(
            db,
            ticker=ticker,
            title=title,
            content=content,
            filename=filename,
            source_type=source_type,
            source_url=url,
            content_type=content_type,
            published_at=published_at,
        )
