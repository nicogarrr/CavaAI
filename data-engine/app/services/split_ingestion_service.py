"""Split ingestion from a labeled data provider (FMP stable/splits).

Ingested splits become UNAPPLIED CorporateAction rows with source
provenance; the user applies them explicitly through the existing
corporate-actions flow, which adjusts position quantities and the FIFO
ledger. Provider failures mark the symbol unavailable; never guessed.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, CorporateAction, Position
from app.services.connectors.fmp import FMPClient
from app.services.provenance import Coverage, SourceKind, provenance
from app.services.company_resolver import resolve_company


class SplitIngestionService:
    def __init__(self, fmp: FMPClient | None = None) -> None:
        self.fmp = fmp or FMPClient()

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        if not value:
            return None
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
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

    async def sync_company(self, db: Session, *, ticker: str) -> dict[str, Any]:
        company = resolve_company(db, ticker)
        if company is None:
            return {"ticker": ticker.upper(), "status": "unknown_company", "inserted": 0, "existing": 0}
        try:
            payload = await self.fmp.splits(company.ticker)
        except Exception as exc:
            return {
                "ticker": company.ticker,
                "status": "unavailable",
                "error": f"{type(exc).__name__}: {exc}"[:300],
                "inserted": 0,
                "existing": 0,
            }
        rows = payload if isinstance(payload, list) else payload.get("historical", [])
        fetched_at = datetime.now(UTC)
        inserted = 0
        existing = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            effective = self._parse_date(row.get("date"))
            ratio = self._parse_ratio(row)
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
                    description=f"Ingested from FMP stable/splits on {fetched_at.date()}; review and apply explicitly.",
                    applied=False,
                    source="fmp",
                    fetched_at=fetched_at,
                )
            )
            inserted += 1
        db.commit()
        return {
            "ticker": company.ticker,
            "status": "ok",
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
                "FMP stable/splits",
                SourceKind.UNOFFICIAL,
                coverage=(
                    Coverage.OK
                    if unavailable == 0
                    else Coverage.PARTIAL if ok else Coverage.UNAVAILABLE
                ),
                note="Splits arrive unapplied; verify against issuer/exchange notices before applying to the ledger.",
            ),
        }
