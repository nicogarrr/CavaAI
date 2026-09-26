"""Dividend record ingestion from labeled data providers (Yahoo, fallback FMP).

Yahoo Finance chart API is the primary source (free, no key); FMP is the
fallback when Yahoo fails (its key may be dead: errors surface as
unavailable, never fabricated). Declared dividends are ingested as deduped
DividendRecord rows with per-row source and fetched_at provenance.
Dividend cash application to the ledger stays manual.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, DividendRecord, Position
from app.services.company_resolver import resolve_company
from app.services.connectors.fmp import FMPClient
from app.services.connectors.yahoo import YahooFinanceClient
from app.services.provenance import Coverage, SourceKind, provenance


class DividendIngestionService:
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
    def _parse_amount(payload: dict) -> Decimal | None:
        for key in ("adjDividend", "dividend", "amount"):
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

    @staticmethod
    def _epoch_to_date(value: Any) -> date | None:
        try:
            return datetime.fromtimestamp(int(value), UTC).date()
        except (TypeError, ValueError, OSError, OverflowError):
            return None

    async def _fetch_rows(
        self, company: Company
    ) -> tuple[list[dict[str, Any]], str]:
        """Normalized (ex_date, amount, pay_date, currency) rows + source label.

        Yahoo first (free, no key); FMP only when Yahoo raises. A successful
        empty Yahoo answer means "no dividends declared", not a failure, so
        it does not trigger the fallback.
        """
        try:
            payload = await self.yahoo.dividends(company.ticker)
        except Exception:
            payload = await self.fmp.dividends(company.ticker)
            rows = payload if isinstance(payload, list) else payload.get("historical", [])
            return [
                {
                    "ex_date": self._parse_date(row.get("date") or row.get("recordDate")),
                    "pay_date": self._parse_date(row.get("paymentDate") or row.get("payDate")),
                    "amount": self._parse_amount(row),
                    "currency": str(row.get("currency") or "USD").upper()[:10],
                }
                for row in rows
                if isinstance(row, dict)
            ], "fmp"
        return [
            {
                "ex_date": self._epoch_to_date(row.get("date")),
                "pay_date": None,  # chart API no expone fecha de pago
                "amount": self._parse_amount(row),
                "currency": (company.currency or "USD").upper()[:10],
            }
            for row in payload
            if isinstance(row, dict)
        ], "yahoo_finance"

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
            rows, source = await self._fetch_rows(company)
        except Exception as exc:  # provider/auth/entitlement/network failure
            return {
                "ticker": company.ticker,
                "status": "unavailable",
                "error": f"{type(exc).__name__}: {exc}"[:300],
                "inserted": 0,
                "existing": 0,
            }
        fetched_at = datetime.now(UTC)
        inserted = 0
        existing = 0
        for row in rows:
            ex_date = row["ex_date"]
            amount = row["amount"]
            if ex_date is None or amount is None:
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
                    pay_date=row["pay_date"],
                    amount=amount,
                    currency=row["currency"],
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
                "Yahoo Finance chart/dividends (fallback FMP stable/dividends)",
                SourceKind.UNOFFICIAL,
                coverage=(
                    Coverage.OK
                    if unavailable == 0
                    else Coverage.PARTIAL if ok else Coverage.UNAVAILABLE
                ),
                note="Declared dividends from data providers; reconcile against issuer/regulator notices for material decisions.",
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
                "Yahoo Finance/FMP dividends via CavaAI Postgres",
                SourceKind.UNOFFICIAL,
                coverage=(
                    Coverage.OK
                    if coverage_ratio >= 1.0
                    else Coverage.PARTIAL if with_data else Coverage.UNAVAILABLE
                ),
                note="Trailing-12-month declared dividends per share over current price; run POST /portfolio/dividends/sync to refresh.",
            ),
        }
