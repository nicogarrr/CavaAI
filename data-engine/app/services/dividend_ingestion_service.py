"""Dividend record ingestion from a labeled data provider (FMP).

Declared dividends are ingested as deduped DividendRecord rows with source
and fetched_at provenance. Provider failures mark the symbol unavailable;
nothing is fabricated. Dividend cash application to the ledger stays manual.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, DividendRecord, Position
from app.services.connectors.fmp import FMPClient
from app.services.provenance import Coverage, SourceKind, provenance
from app.services.company_resolver import resolve_company


class DividendIngestionService:
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
    def _parse_amount(payload: dict) -> Decimal | None:
        for key in ("adjDividend", "dividend"):
            raw = payload.get(key)
            if raw is None:
                continue
            try:
                amount = Decimal(str(raw))
            except (InvalidOperation, ValueError):
                continue
            if amount > 0:
                return amount
        return None

    async def sync_company(self, db: Session, *, ticker: str) -> dict[str, Any]:
        """Ingest declared dividends for one company. Returns counts + provenance."""
        company = resolve_company(db, ticker)
        if company is None:
            return {
                "ticker": ticker.upper(),
                "status": "unknown_company",
                "inserted": 0,
                "existing": 0,
            }
        try:
            payload = await self.fmp.dividends(company.ticker)
        except Exception as exc:  # provider/auth/entitlement/network failure
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
            ex_date = self._parse_date(row.get("date") or row.get("recordDate"))
            if ex_date is None:
                continue
            amount = self._parse_amount(row)
            if amount is None:
                continue
            duplicate = db.scalar(
                select(DividendRecord).where(
                    DividendRecord.company_id == company.id,
                    DividendRecord.ex_date == ex_date,
                    DividendRecord.amount == amount,
                )
            )
            if duplicate is not None:
                existing += 1
                continue
            db.add(
                DividendRecord(
                    company_id=company.id,
                    ex_date=ex_date,
                    pay_date=self._parse_date(row.get("paymentDate") or row.get("payDate")),
                    amount=amount,
                    currency=str(row.get("currency") or "USD").upper()[:10],
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
        """Ingest dividends for every currently held company."""
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
                "FMP stable/dividends",
                SourceKind.UNOFFICIAL,
                coverage=(
                    Coverage.OK
                    if unavailable == 0
                    else Coverage.PARTIAL if ok else Coverage.UNAVAILABLE
                ),
                note="Declared dividends from a data provider; reconcile against issuer/regulator notices for material decisions.",
            ),
        }

    def portfolio_yields(self, db: Session) -> dict[str, Any]:
        """Trailing-12-month dividend yield per held position + portfolio aggregate.

        Yield = TTM declared dividends per share / current market price, both in
        the position's native currency. Positions whose dividend currency does
        not match the price currency are excluded from yield math and counted
        honestly in coverage instead of being silently converted.
        """
        cutoff = date.today().replace(year=date.today().year - 1)
        rows = list(
            db.execute(
                select(Position, Company).join(Company, Position.company_id == Company.id)
            ).all()
        )
        positions = []
        with_data = 0
        weighted_yield = 0.0
        total_value = 0.0
        for position, company in rows:
            records = list(
                db.scalars(
                    select(DividendRecord).where(
                        DividendRecord.company_id == company.id,
                        DividendRecord.ex_date >= cutoff,
                    )
                ).all()
            )
            price = float(position.market_price or 0)
            value = float(position.market_value_base or position.market_value or 0)
            total_value += value
            matching_currency = [r for r in records if r.currency == position.currency]
            ttm = sum(float(r.amount) for r in matching_currency)
            skipped_currency = len(records) - len(matching_currency)
            dividend_yield = (ttm / price) if price > 0 and records else None
            if records:
                with_data += 1
                if dividend_yield is not None and value > 0:
                    weighted_yield += dividend_yield * value
            positions.append(
                {
                    "ticker": company.ticker,
                    "ttm_dividend_per_share": ttm if records else None,
                    "currency": position.currency,
                    "price": price or None,
                    "dividend_yield": dividend_yield,
                    "records_12m": len(records),
                    "skipped_currency_mismatch": skipped_currency,
                    "last_fetched_at": (
                        max(r.fetched_at for r in records).isoformat()
                        if records and all(r.fetched_at for r in records)
                        else None
                    ),
                }
            )
        coverage_ratio = (with_data / len(rows)) if rows else 1.0
        return {
            "as_of": date.today().isoformat(),
            "positions": positions,
            "portfolio_yield": (weighted_yield / total_value) if total_value > 0 else None,
            "coverage": {
                "positions": len(rows),
                "positions_with_dividend_data": with_data,
                "percent": round(100 * coverage_ratio, 1),
            },
            "provenance": provenance(
                "FMP stable/dividends via CavaAI Postgres",
                SourceKind.UNOFFICIAL,
                coverage=(
                    Coverage.OK
                    if coverage_ratio >= 1.0
                    else Coverage.PARTIAL if with_data else Coverage.UNAVAILABLE
                ),
                note="Trailing-12-month declared dividends per share over current price; run POST /portfolio/dividends/sync to refresh.",
            ),
        }
