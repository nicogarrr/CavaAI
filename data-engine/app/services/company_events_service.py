"""Eventos de resultados e índice de filings por compañía (ficha Quartr-like, Fase 1).

Fuentes gratuitas, todo con fuente y fecha; la ausencia es un estado honesto,
nunca un dato inventado:

- Finnhub ``/calendar/earnings`` (tier gratis): próxima fecha de resultados,
  hora (bmo/amc) y estimaciones de EPS/ingresos.
- Finnhub ``/stock/earnings`` (tier gratis): historial de 4 trimestres con
  EPS real vs estimado y sorpresa.
- SEC EDGAR submissions (data.sec.gov, sin key): índice de filings
  10-K/10-Q/8-K/DEF 14A... con fecha y enlace directo a sec.gov (lo abre el
  navegador del usuario; la VM no descarga el documento).

Nunca lanza por red: cada fuente degrada a ``status="unavailable"`` con el
motivo. La red es inyectable (tests herméticos sin salir a internet).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, Document
from app.core.errors import redact_secrets
from app.services.connectors.finnhub import FinnhubClient
from app.services.connectors.sec import SECClient

logger = logging.getLogger(__name__)

FILING_FORMS = (
    "10-K",
    "10-K/A",
    "10-Q",
    "10-Q/A",
    "8-K",
    "8-K/A",
    "DEF 14A",
    "20-F",
    "6-K",
)

CALENDAR_CHUNK_DAYS = 90
CALENDAR_PAST_DAYS = 400
CALENDAR_FUTURE_DAYS = 120

# Tipo de los fetchers inyectables: mismas firmas que los métodos reales.
CalendarFetcher = Callable[[str, str], Awaitable[dict[str, Any] | None]]
EpsHistoryFetcher = Callable[[str], Awaitable[list[dict[str, Any]] | None]]
SubmissionsFetcher = Callable[[str], Awaitable[dict[str, Any] | None]]
CikFetcher = Callable[[str], Awaitable[str | None]]


def _utcnow() -> datetime:
    return datetime.now(UTC)


class CompanyEventsService:
    def __init__(
        self,
        db: Session,
        *,
        calendar_fetcher: CalendarFetcher | None = None,
        eps_history_fetcher: EpsHistoryFetcher | None = None,
        submissions_fetcher: SubmissionsFetcher | None = None,
        cik_fetcher: CikFetcher | None = None,
    ) -> None:
        self.db = db
        self._finnhub = FinnhubClient()
        self._sec = SECClient()
        self._calendar_fetcher = calendar_fetcher or self._fetch_calendar_chunk
        self._eps_fetcher = eps_history_fetcher or self._fetch_eps_history
        self._submissions_fetcher = submissions_fetcher or self._fetch_submissions
        self._cik_fetcher = cik_fetcher or self._fetch_cik

    # ------------------------------------------------------------------
    # Fetchers reales (envoltura fina sobre los connectors)
    # ------------------------------------------------------------------
    async def _fetch_calendar_chunk(
        self, from_date: str, to_date: str
    ) -> dict[str, Any] | None:
        if not self._finnhub.configured():
            return None
        try:
            payload = await self._finnhub._get(
                "/calendar/earnings", {"from": from_date, "to": to_date}
            )
        except Exception as exc:  # red, 4xx/5xx, timeout: degradación honesta
            logger.warning("finnhub calendar/earnings %s→%s falló: %s", from_date, to_date, redact_secrets(str(exc)))
            return None
        return payload if isinstance(payload, dict) else None

    async def _fetch_eps_history(self, symbol: str) -> list[dict[str, Any]] | None:
        if not self._finnhub.configured():
            return None
        try:
            payload = await self._finnhub._get("/stock/earnings", {"symbol": symbol})
        except Exception as exc:
            logger.warning("finnhub stock/earnings %s falló: %s", symbol, redact_secrets(str(exc)))
            return None
        return payload if isinstance(payload, list) else None

    async def _fetch_submissions(self, cik: str) -> dict[str, Any] | None:
        try:
            payload = await self._sec.submissions(cik)
        except Exception as exc:
            logger.warning("EDGAR submissions CIK%s falló: %s", cik, exc)
            return None
        return payload if isinstance(payload, dict) else None

    async def _fetch_cik(self, ticker: str) -> str | None:
        try:
            return await self._sec.cik_for_ticker(ticker)
        except Exception as exc:
            logger.warning("EDGAR cik_for_ticker %s falló: %s", ticker, exc)
            return None

    # ------------------------------------------------------------------
    # Eventos de resultados
    # ------------------------------------------------------------------
    async def get_events(self, company: Company) -> dict[str, Any]:
        today = _utcnow().date()
        chunks: list[tuple[date, date]] = []
        start = today - timedelta(days=CALENDAR_PAST_DAYS)
        while start < today + timedelta(days=CALENDAR_FUTURE_DAYS):
            end = min(start + timedelta(days=CALENDAR_CHUNK_DAYS - 1),
                      today + timedelta(days=CALENDAR_FUTURE_DAYS))
            chunks.append((start, end))
            start = end + timedelta(days=1)

        calendar_rows: list[dict[str, Any]] = []
        calendar_ok = False
        for chunk_start, chunk_end in chunks:
            payload = await self._calendar_fetcher(
                chunk_start.isoformat(), chunk_end.isoformat()
            )
            if payload is None:
                continue
            calendar_ok = True
            for row in payload.get("earningsCalendar") or []:
                if str(row.get("symbol", "")).upper() == company.ticker.upper():
                    calendar_rows.append(row)

        eps_rows = await self._eps_fetcher(company.ticker)

        next_event = self._next_event(calendar_rows, today)
        history = self._history(calendar_rows, eps_rows, today)

        return {
            "ticker": company.ticker,
            "company_name": company.name,
            "as_of": _utcnow().isoformat(),
            "calendar_status": "ok" if calendar_ok else "unavailable",
            "eps_history_status": "ok" if eps_rows is not None else "unavailable",
            "next_event": next_event,
            "history": history,
            "source": "Finnhub (calendar/earnings + stock/earnings, tier gratuito)",
            "note": None
            if (calendar_ok or eps_rows is not None)
            else "Sin datos de calendario de resultados: Finnhub no disponible o sin cobertura para este ticker.",
        }

    @staticmethod
    def _parse_day(value: Any) -> date | None:
        if not value:
            return None
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None

    def _next_event(
        self, rows: list[dict[str, Any]], today: date
    ) -> dict[str, Any] | None:
        future = [
            row for row in rows
            if (day := self._parse_day(row.get("date"))) is not None and day >= today
        ]
        if not future:
            return None
        row = min(future, key=lambda r: self._parse_day(r.get("date")) or today)
        return {
            "date": row.get("date"),
            "hour": row.get("hour") or None,
            "quarter": row.get("quarter"),
            "year": row.get("year"),
            "eps_estimate": row.get("epsEstimate"),
            "revenue_estimate": row.get("revenueEstimate"),
            "source": "Finnhub /calendar/earnings",
        }

    def _history(
        self,
        calendar_rows: list[dict[str, Any]],
        eps_rows: list[dict[str, Any]] | None,
        today: date,
    ) -> list[dict[str, Any]]:
        by_period: dict[str, dict[str, Any]] = {}
        for row in calendar_rows:
            day = self._parse_day(row.get("date"))
            if day is None or day >= today:
                continue
            period = day.isoformat()
            by_period[period] = {
                "period": period,
                "quarter": row.get("quarter"),
                "year": row.get("year"),
                "eps_estimate": row.get("epsEstimate"),
                "eps_actual": row.get("epsActual"),
                "revenue_estimate": row.get("revenueEstimate"),
                "revenue_actual": row.get("revenueActual"),
                "eps_surprise_percent": None,
                "source": "Finnhub /calendar/earnings",
            }
        for row in eps_rows or []:
            period = str(row.get("period") or "")
            if not period:
                continue
            entry = by_period.setdefault(
                period,
                {
                    "period": period,
                    "quarter": row.get("quarter"),
                    "year": row.get("year"),
                    "eps_estimate": None,
                    "eps_actual": None,
                    "revenue_estimate": None,
                    "revenue_actual": None,
                    "eps_surprise_percent": None,
                    "source": "Finnhub /stock/earnings",
                },
            )
            if entry["eps_estimate"] is None:
                entry["eps_estimate"] = row.get("estimate")
            if entry["eps_actual"] is None:
                entry["eps_actual"] = row.get("actual")
            entry["eps_surprise_percent"] = row.get("surprisePercent")
        return sorted(
            by_period.values(), key=lambda item: item["period"], reverse=True
        )[:8]

    # ------------------------------------------------------------------
    # Índice de filings
    # ------------------------------------------------------------------
    async def get_filings(self, company: Company, *, limit: int = 40) -> dict[str, Any]:
        cik = company.cik or await self._cik_fetcher(company.ticker)
        filings: list[dict[str, Any]] = []
        sec_status = "unavailable"
        note: str | None = None

        if cik:
            payload = await self._submissions_fetcher(str(cik).zfill(10))
            if payload is not None:
                sec_status = "ok"
                filings = self._map_submissions(str(cik), payload, company.ticker, limit)
            else:
                note = "SEC EDGAR no accesible desde el servidor en este momento."
        if not filings:
            db_docs = self._db_documents(company, limit)
            if db_docs:
                note = note or "Sin índice SEC; se listan documentos ya importados."
        return {
            "ticker": company.ticker,
            "company_name": company.name,
            "as_of": _utcnow().isoformat(),
            "sec_status": sec_status,
            "filings": filings,
            "documents": self._db_documents(company, limit),
            "source": "SEC EDGAR (data.sec.gov)" if filings else None,
            "note": note
            or (None if filings else "Sin filings SEC para este ticker (¿compañía no estadounidense?). Documentos ESEF/CNMV llegan en Fase 2."),
        }

    @staticmethod
    def _column(recent: dict[str, Any], name: str, index: int) -> Any:
        values = recent.get(name) or []
        return values[index] if index < len(values) else None

    def _map_submissions(
        self, cik: str, payload: dict[str, Any], ticker: str, limit: int
    ) -> list[dict[str, Any]]:
        recent = (payload.get("filings") or {}).get("recent") or {}
        accessions = recent.get("accessionNumber") or []
        allowed = {form.upper() for form in FILING_FORMS}
        items: list[dict[str, Any]] = []
        for index, accession in enumerate(accessions):
            form = self._column(recent, "form", index)
            if not form or str(form).upper() not in allowed:
                continue
            primary_document = self._column(recent, "primaryDocument", index)
            try:
                url = (
                    SECClient.filing_document_url(cik, str(accession), str(primary_document))
                    if primary_document
                    else SECClient.filing_index_url(cik, str(accession))
                )
            except ValueError:
                continue
            items.append(
                {
                    "form": str(form),
                    "filed_at": self._column(recent, "filingDate", index),
                    "period": self._column(recent, "reportDate", index),
                    "accession": str(accession),
                    "url": url,
                    "source": "SEC EDGAR",
                }
            )
            if len(items) >= limit:
                break
        return items

    def _db_documents(self, company: Company, limit: int) -> list[dict[str, Any]]:
        rows = self.db.execute(
            select(Document)
            .where(Document.company_id == company.id)
            .order_by(Document.created_at.desc())
            .limit(limit)
        ).scalars().all()
        return [
            {
                "title": row.title,
                "source_type": row.source_type,
                "url": row.source_url,
                "published_at": row.published_at.isoformat() if row.published_at else None,
                "imported_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
