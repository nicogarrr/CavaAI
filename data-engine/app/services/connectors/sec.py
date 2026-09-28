from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from pathlib import PurePosixPath
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings
from app.services.connectors import sec_edgar
from app.services.connectors.base import ConnectorItem, ConnectorResult

# Filings que declaran un cierre de ejercicio anual. Las enmiendas (10-K/A)
# re-declaran el mismo cierre y sirven de ancla para valores re-expresados.
ANNUAL_REPORT_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}


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
        snapshot = sec_edgar.read_snapshot_for(url)
        if snapshot is not None:
            return snapshot
        try:
            return (await self._get(url)).json()
        except httpx.HTTPStatusError as exc:
            # La SEC bloquea IPs de datacenter con 403: el mirror HF sirve el
            # mismo JSON oficial. Un 404 de la SEC es un fallo de DATO y
            # nunca se enmascara como fallo de transporte.
            if exc.response is not None and exc.response.status_code in {401, 403}:
                return await sec_edgar.mirror_get_json(url, direct_error=exc)
            raise

    async def ticker_map(self) -> dict:
        return await self._get_json(self.ticker_map_url)

    async def cik_for_ticker(self, ticker: str) -> str | None:
        ticker = ticker.upper()
        manifest_cik = sec_edgar.manifest_cik(ticker)
        if manifest_cik:
            return manifest_cik
        mapping = await self.ticker_map()
        for item in mapping.values():
            if item.get("ticker", "").upper() == ticker:
                return str(item["cik_str"]).zfill(10)
        return None

    async def submissions(self, cik: str) -> dict:
        padded = str(cik).zfill(10)
        return await self._get_json(f"{self.submissions_url}/CIK{padded}.json")

    async def annual_report_anchors(self, cik: str) -> dict[str, str]:
        """{accessionNumber: reportDate} de los filings anuales del emisor.

        Es la evidencia de calendario fiscal a nivel de filing: cada 10-K
        declara en portada el cierre del ejercicio que reporta. La ingesta
        anual ancla cada hecho a su filing por `accn` en vez de inferir el
        calendario por moda de hechos (una moda es envenenable con ruido TTM
        coherentemente distribuido; una fecha de portada, no). Fusiona
        `recent` con los ficheros historicos de submissions; si un fichero
        historico falla se sigue con cobertura parcial (visible en el
        resultado de la ingesta), nunca se sustituye por inferencia.
        """
        payload = await self.submissions(cik)
        filings = payload.get("filings", {})
        anchors: dict[str, str] = {}

        def _absorb(recent: dict) -> None:
            forms = recent.get("form", [])
            accessions = recent.get("accessionNumber", [])
            report_dates = recent.get("reportDate", [])
            for index, accession in enumerate(accessions):
                form = str(forms[index]) if index < len(forms) else ""
                if form not in ANNUAL_REPORT_FORMS:
                    continue
                report_date = (
                    str(report_dates[index]) if index < len(report_dates) else ""
                )
                if accession and report_date:
                    anchors[str(accession)] = report_date

        _absorb(filings.get("recent", {}))
        for extra in filings.get("files", []) or []:
            name = extra.get("name") if isinstance(extra, dict) else None
            if not name:
                continue
            try:
                _absorb(await self._get_json(f"{self.submissions_url}/{name}"))
            except Exception:  # noqa: BLE001 - cobertura parcial > romper la ingesta
                continue
        return anchors

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
                # Titular en español, sin ticker ni fecha: la UI los muestra
                # en campos propios (columna ticker, fecha del evento) y el
                # titular no debe repetirlos (quick win UX 4). El summary
                # queda vacío: la frase ES ya es el titular; un resumen
                # adicional duplicaría el texto en la ingesta de noticias.
                # headline_from_source=False: la SEC no publica un titular
                # para el filing, este texto ES de display creado por CavaAI
                # y NO debe persistir como source_headline (procedencia).
                title = f"{form or 'filing'} presentado ante la SEC"
                items.append(
                    ConnectorItem(
                        source="SEC",
                        title=title,
                        url=url,
                        summary="",
                        published_at=self._filing_datetime(filing_date),
                        ticker=ticker.upper() if ticker else None,
                        item_type="filing",
                        headline_from_source=False,
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

