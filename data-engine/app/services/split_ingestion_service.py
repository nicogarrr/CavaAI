"""Split ingestion from labeled data providers (Yahoo, fallback FMP).

Yahoo Finance chart API is the primary source (free, no key); FMP stable/
splits is the fallback when Yahoo fails (its key may be dead: errors
surface as unavailable, never guessed). Ingested splits become UNAPPLIED
CorporateAction rows with per-row source provenance; the user applies them
explicitly through the existing corporate-actions flow, which adjusts
position quantities and the FIFO ledger.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, CorporateAction, Position
from app.core.errors import redact_secrets
from app.services.connectors.fmp import FMPClient
from app.services.connectors.yahoo import YahooFinanceClient
from app.services.provenance import Coverage, SourceKind, provenance
from app.services.company_resolver import resolve_company


class SplitIngestionService:
    def __init__(
        self,
        fmp: FMPClient | None = None,
        yahoo: YahooFinanceClient | None = None,
    ) -> None:
        self.fmp = fmp or FMPClient()
        self.yahoo = yahoo or YahooFinanceClient()

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        if not value:
            return None
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None

    @staticmethod
    def _epoch_to_date(value: Any) -> date | None:
        try:
            return datetime.fromtimestamp(int(value), UTC).date()
        except (TypeError, ValueError, OSError, OverflowError):
            return None

    @staticmethod
    def _parse_ratio(row: dict) -> Decimal | None:
        """Shares after / shares before from numerator/denominator fields."""
        try:
            numerator = Decimal(str(row.get("numerator")))
            denominator = Decimal(str(row.get("denominator")))
        except (InvalidOperation, ValueError, TypeError):
            return None
        if denominator <= 0 or numerator <= 0:
            return None
        return numerator / denominator

    async def _fetch_rows(
        self, company: Company
    ) -> tuple[list[dict[str, Any]], str]:
        """Normalized (effective_date, ratio) rows + source label.

        Yahoo first (free, no key); FMP only when Yahoo raises. A successful
        empty Yahoo answer means "no splits", not a failure, so it does not
        trigger the fallback.
        """
        try:
            payload = await self.yahoo.splits(company.ticker)
        except Exception:
            payload = await self.fmp.splits(company.ticker)
            rows = payload if isinstance(payload, list) else payload.get("historical", [])
            return [
                {
                    "effective_date": self._parse_date(row.get("date")),
                    "ratio": self._parse_ratio(row),
                }
                for row in rows
                if isinstance(row, dict)
            ], "fmp"
        return [
            {
                "effective_date": self._epoch_to_date(row.get("date")),
                "ratio": self._parse_ratio(row),
            }
            for row in payload
            if isinstance(row, dict)
        ], "yahoo_finance"

    async def sync_company(self, db: Session, *, ticker: str) -> dict[str, Any]:
        company = resolve_company(db, ticker)
        if company is None:
            return {"ticker": ticker.upper(), "status": "unknown_company", "inserted": 0, "existing": 0}
        try:
            rows, source = await self._fetch_rows(company)
        except Exception as exc:
            return {
                "ticker": company.ticker,
                "status": "unavailable",
                "error": redact_secrets(f"{type(exc).__name__}: {exc}")[:300],
                "inserted": 0,
                "existing": 0,
            }
        fetched_at = datetime.now(UTC)
        inserted = 0
        existing = 0
        for row in rows:
            effective = row["effective_date"]
            ratio = row["ratio"]
            if effective is None or ratio is None:
                continue
            duplicate = db.scalar(
                select(CorporateAction).where(
                    CorporateAction.company_id == company.id,
                    CorporateAction.effective_date == effective,
                    CorporateAction.ratio == ratio,
                    CorporateAction.action_type.in_(["split", "reverse_split"]),
                )
            )
            if duplicate is not None:
                existing += 1
                continue
            db.add(
                CorporateAction(
                    company_id=company.id,
                    action_type="split" if ratio > 1 else "reverse_split",
                    effective_date=effective,
                    ratio=ratio,
                    description=f"Ingested from {source} on {fetched_at.date()}; review and apply explicitly.",
                    applied=False,
                    source=source,
                    fetched_at=fetched_at,
                )
            )
            inserted += 1
        db.commit()
        return {
            "ticker": company.ticker,
            "status": "ok",
            "source": source,
            "inserted": inserted,
            "existing": existing,
            "fetched_at": fetched_at.isoformat(),
        }

    async def sync_portfolio(self, db: Session) -> dict[str, Any]:
        company_ids = db.scalars(select(Position.company_id).distinct()).all()
        tickers = list(
            db.scalars(select(Company.ticker).where(Company.id.in_(company_ids))).all()
        ) if company_ids else []
        results = [await self.sync_company(db, ticker=ticker) for ticker in tickers]
        ok = sum(1 for r in results if r["status"] == "ok")
        unavailable = sum(1 for r in results if r["status"] == "unavailable")
        return {
            "companies": len(results),
            "synced": ok,
            "unavailable": unavailable,
            "results": results,
            "provenance": provenance(
                "Yahoo Finance chart/splits (fallback FMP stable/splits)",
                SourceKind.UNOFFICIAL,
                coverage=(
                    Coverage.OK
                    if unavailable == 0
                    else Coverage.PARTIAL if ok else Coverage.UNAVAILABLE
                ),
                note="Splits arrive unapplied; verify against issuer/exchange notices before applying to the ledger.",
            ),
        }
