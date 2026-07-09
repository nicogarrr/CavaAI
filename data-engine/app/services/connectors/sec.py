from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from pathlib import PurePosixPath
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings
from app.services.connectors.base import ConnectorItem, ConnectorResult


class SECClient:
    submissions_url = "https://data.sec.gov/submissions"
    companyfacts_url = "https://data.sec.gov/api/xbrl/companyfacts"
    ticker_map_url = "https://www.sec.gov/files/company_tickers.json"
    archives_url = "https://www.sec.gov/Archives/edgar/data"

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        user_agent: str | None = None,
        requests_per_second: float = 8,
    ) -> None:
        self.settings = get_settings()
        self.client = client
        self.user_agent = user_agent or self.settings.sec_user_agent
        self._minimum_interval = 1 / max(0.1, min(requests_per_second, 10))
        self._last_request_at = 0.0
        self._rate_lock = asyncio.Lock()

    @property
    def headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Accept": "application/json, text/html, */*",
        }

    async def _throttle(self) -> None:
        async with self._rate_lock:
            elapsed = time.monotonic() - self._last_request_at
            delay = self._minimum_interval - elapsed
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_request_at = time.monotonic()

    async def _get(self, url: str) -> httpx.Response:
        await self._throttle()
        if self.client is not None:
            response = await self.client.get(url, headers=self.headers)
        else:
            async with httpx.AsyncClient(
                timeout=30,
                headers=self.headers,
                follow_redirects=True,
            ) as client:
                response = await client.get(url)
        response.raise_for_status()
        return response

    async def _get_json(self, url: str) -> dict:
        return (await self._get(url)).json()

    async def ticker_map(self) -> dict:
        return await self._get_json(self.ticker_map_url)

    async def cik_for_ticker(self, ticker: str) -> str | None:
        ticker = ticker.upper()
        mapping = await self.ticker_map()
        for item in mapping.values():
            if item.get("ticker", "").upper() == ticker:
                return str(item["cik_str"]).zfill(10)
        return None

    async def submissions(self, cik: str) -> dict:
        padded = str(cik).zfill(10)
        return await self._get_json(f"{self.submissions_url}/CIK{padded}.json")

    async def company_facts(self, cik: str) -> dict:
        padded = str(cik).zfill(10)
        return await self._get_json(f"{self.companyfacts_url}/CIK{padded}.json")

    @classmethod
    def filing_index_url(cls, cik: str, accession_number: str) -> str:
        cik_number = str(int(str(cik)))
        accession = accession_number.replace("-", "")
        if not accession.isdigit():
            raise ValueError("SEC accession number must contain only digits and hyphens")
        return f"{cls.archives_url}/{cik_number}/{accession}/"

    @classmethod
    def filing_document_url(
        cls,
        cik: str,
        accession_number: str,
        primary_document: str,
    ) -> str:
        filename = PurePosixPath(primary_document).name
        if not filename or filename in {".", ".."}:
            raise ValueError("SEC primary document filename is required")
        return f"{cls.filing_index_url(cik, accession_number)}{filename}"

    async def recent_filings(
        self,
        cik: str,
        *,
        forms: set[str] | list[str] | tuple[str, ...] | None = None,
        limit: int = 40,
        ticker: str | None = None,
    ) -> ConnectorResult:
        metadata = {
            "cik": str(cik).zfill(10),
            "ticker": ticker,
            "forms": sorted(forms) if forms else None,
        }
        try:
            payload = await self.submissions(cik)
            recent = payload.get("filings", {}).get("recent", {})
            allowed_forms = {form.upper() for form in forms} if forms else None
            accessions = recent.get("accessionNumber", [])
            items: list[ConnectorItem] = []
            if limit <= 0:
                return ConnectorResult(source="sec", items=[], metadata=metadata)
            for index, accession in enumerate(accessions):
                form = self._column(recent, "form", index)
                if allowed_forms and str(form).upper() not in allowed_forms:
                    continue
                primary_document = self._column(recent, "primaryDocument", index)
                if not primary_document:
                    url = self.filing_index_url(cik, str(accession))
                else:
                    url = self.filing_document_url(cik, str(accession), str(primary_document))
                filing_date = self._column(recent, "filingDate", index)
                report_date = self._column(recent, "reportDate", index)
                title = f"{ticker.upper() + ' ' if ticker else ''}{form or 'SEC filing'}"
                if report_date:
                    title = f"{title} ({report_date})"
                items.append(
                    ConnectorItem(
                        source="SEC",
                        title=title,
                        url=url,
                        summary=(
                            f"SEC {form or 'filing'} filed {filing_date or 'on an unknown date'}"
                        ),
                        published_at=self._filing_datetime(filing_date),
                        ticker=ticker.upper() if ticker else None,
                        item_type="filing",
                        external_id=str(accession),
                        metadata={
                            "cik": str(cik).zfill(10),
                            "accession_number": accession,
                            "form": form,
                            "filing_date": filing_date,
                            "report_date": report_date,
                            "primary_document": primary_document,
                            "is_inline_xbrl": self._column(recent, "isInlineXBRL", index),
                        },
                    )
                )
                if len(items) >= limit:
                    break
            metadata["company_name"] = payload.get("name")
            return ConnectorResult(source="sec", items=items, metadata=metadata)
        except Exception as exc:
            return ConnectorResult.failed("sec", exc, metadata=metadata)

    async def filing_document(self, url: str) -> tuple[bytes, str | None]:
        """Download a filing with the same SEC identity and request throttle."""

        hostname = urlparse(url).hostname or ""
        if hostname.lower() not in {"sec.gov", "www.sec.gov"}:
            raise ValueError("SEC filing URL must use sec.gov")
        response = await self._get(url)
        return response.content, response.headers.get("content-type")

    @staticmethod
    def _column(recent: dict, name: str, index: int):
        values = recent.get(name, [])
        return values[index] if index < len(values) else None

    @staticmethod
    def _filing_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            return None

