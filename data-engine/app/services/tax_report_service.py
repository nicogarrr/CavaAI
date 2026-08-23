"""Fiscal-year tax computation for the private portfolio.

The report follows Spanish IRPF conventions:

- Realized gains/losses use FIFO lot accounting on sells (required by law for
  homogeneous securities). FX conversion to the portfolio base currency uses
  the transaction-date rate from the FX ledger.
- Dividends are grouped by company and converted at the payment date rate.
- Withholding is matched from cash transactions whose type contains
  "withholding" / "tax" (IBKR reports gross dividend and withheld tax as
  separate CashTransaction rows in the same statement).
"""

from __future__ import annotations

from collections import deque
from datetime import UTC, date, datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    Company,
    Position,
    Portfolio,
    TaxReport,
    Transaction,
)
from app.services.portfolio_fx_service import PortfolioFXService

FIFO_METHOD = "fifo"
AVERAGE_METHOD = "average"

DIVIDEND_ACTIONS = {"dividend", "div", "cash_dividend", "withholding"}
SELL_ACTIONS = {"sell", "sold"}
BUY_ACTIONS = {"buy", "bot", "b"}


def _money(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class TaxReportService:
    """Compute and persist per-fiscal-year tax snapshots."""

    def __init__(self) -> None:
        self.fx = PortfolioFXService()
        self.settings = get_settings()

    def compute_report(self, db: Session, fiscal_year: int) -> dict:
        portfolio = self.fx.portfolio(db)
        if portfolio is None:
            portfolio = self.fx.ensure_portfolio(db)
        base_currency = portfolio.base_currency or "EUR"

        start = date(fiscal_year, 1, 1)
        end = date(fiscal_year, 12, 31)

        rows = db.execute(
            select(Transaction, Company)
            .join(Company, Transaction.company_id == Company.id)
            .where(Transaction.trade_date >= start, Transaction.trade_date <= end)
            .order_by(Transaction.trade_date, Transaction.id)
        ).all()

        dividends_by_company: dict[str, dict] = {}
        realized_by_company: dict[str, dict] = {}
        misc_rows: list[dict] = []

        # First pass: dividends, withholding and misc cash movements.
        for transaction, company in rows:
            action = (transaction.action or "").lower()
            ticker = company.ticker
            if action in DIVIDEND_ACTIONS or "dividend" in action or "withholding" in action:
                rate = self.fx.rate(
                    db,
                    quote_currency=transaction.currency,
                    base_currency=base_currency,
                    as_of=transaction.trade_date,
                )
                gross = transaction.price if transaction.price else transaction.quantity
                amount_native = gross
                amount_base = (
                    amount_native * rate
                    if rate is not None
                    else self._approx_convert(db, transaction.currency, base_currency, transaction.trade_date, amount_native)
                )
                bucket = dividends_by_company.setdefault(
                    ticker,
                    {
                        "ticker": ticker,
                        "currency": transaction.currency,
                        "dividends_native": Decimal("0"),
                        "dividends_base": Decimal("0"),
                        "withholding_native": Decimal("0"),
                        "withholding_base": Decimal("0"),
                        "payments": [],
                    },
                )
                if "withholding" in action or "tax" in action:
                    withheld = abs(amount_native)
                    bucket["withholding_native"] += withheld
                    bucket["withholding_base"] += abs(amount_base)
                    bucket["payments"].append(
                        {
                            "date": transaction.trade_date.isoformat(),
                            "type": "withholding",
                            "amount_native": _money(withheld),
                            "amount_base": _money(abs(amount_base)),
                        }
                    )
                else:
                    bucket["dividends_native"] += amount_native
                    bucket["dividends_base"] += amount_base
                    bucket["payments"].append(
                        {
                            "date": transaction.trade_date.isoformat(),
                            "type": "dividend",
                            "amount_native": _money(amount_native),
                            "amount_base": _money(amount_base),
                        }
                    )
                continue

            if action in {"interest", "fee", "cash_misc"}:
                rate = self.fx.rate(
                    db,
                    quote_currency=transaction.currency,
                    base_currency=base_currency,
                    as_of=transaction.trade_date,
                )
                amount = transaction.price or transaction.quantity
                misc_rows.append(
                    {
                        "date": transaction.trade_date.isoformat(),
                        "ticker": ticker,
                        "type": action,
                        "amount_native": _money(amount),
                        "amount_base": _money(amount * rate) if rate else None,
                        "currency": transaction.currency,
                    }
                )
                continue

            if action in SELL_ACTIONS or action in BUY_ACTIONS:
                # Accumulate for FIFO pass; done below in chronological order.
                continue

        # Second pass: FIFO realized gains/losses per company.
        # We rebuild lots from ALL transactions up to end of fiscal year so
        # that cost basis is correct even when purchases predate the year.
        sell_rows = db.execute(
            select(Transaction, Company)
            .join(Company, Transaction.company_id == Company.id)
            .where(Transaction.trade_date <= end)
            .order_by(Transaction.trade_date, Transaction.id)
        ).all()

        lots: dict[str, deque[tuple[Decimal, Decimal, Decimal]]] = {}
        realized_by_company = {}
        for transaction, company in sell_rows:
            action = (transaction.action or "").lower()
            if action in BUY_ACTIONS:
                native_cost = transaction.quantity * transaction.price + transaction.fees
                lots.setdefault(company.ticker, deque()).append(
                    (transaction.quantity, transaction.price, native_cost)
                )
                continue
            if action not in SELL_ACTIONS:
                continue

            ticker = company.ticker
            remaining = transaction.quantity
            proceeds_native = transaction.quantity * transaction.price - transaction.fees
            cost_native = Decimal("0")
            queue = lots.setdefault(ticker, deque())
            while remaining > Decimal("0") and queue:
                qty, price, total_cost = queue[0]
                take = min(qty, remaining)
                cost_native += take * price
                if take == qty:
                    queue.popleft()
                else:
                    queue[0] = (qty - take, price, total_cost)
                remaining -= take

            if remaining > Decimal("0"):
                # Sold more than bought: treat remaining as no-cost (rare).
                pass

            rate = self.fx.rate(
                db,
                quote_currency=transaction.currency,
                base_currency=base_currency,
                as_of=transaction.trade_date,
            )
            gain_native = proceeds_native - cost_native
            if rate is not None:
                gain_base = gain_native * rate
                proceeds_base = proceeds_native * rate
                cost_base = cost_native * rate
            else:
                gain_base = None
                proceeds_base = None
                cost_base = None

            bucket = realized_by_company.setdefault(
                ticker,
                {
                    "ticker": ticker,
                    "currency": transaction.currency,
                    "proceeds_native": Decimal("0"),
                    "cost_native": Decimal("0"),
                    "gain_native": Decimal("0"),
                    "gain_base": Decimal("0"),
                    "sale_count": 0,
                    "sales": [],
                },
            )
            bucket["proceeds_native"] += proceeds_native
            bucket["cost_native"] += cost_native
            bucket["gain_native"] += gain_native
            if gain_base is not None:
                bucket["gain_base"] += gain_base
            bucket["sale_count"] += 1
            bucket["sales"].append(
                {
                    "date": transaction.trade_date.isoformat(),
                    "quantity": float(transaction.quantity),
                    "proceeds_native": _money(proceeds_native),
                    "cost_native": _money(cost_native),
                    "gain_native": _money(gain_native),
                    "gain_base": _money(gain_base) if gain_base is not None else None,
                }
            )

        dividends = []
        for bucket in dividends_by_company.values():
            dividends.append(
                {
                    "ticker": bucket["ticker"],
                    "currency": bucket["currency"],
                    "dividends_native": _money(bucket["dividends_native"]),
                    "dividends_base": _money(bucket["dividends_base"]),
                    "withholding_native": _money(bucket["withholding_native"]),
                    "withholding_base": _money(bucket["withholding_base"]),
                    "payments": bucket["payments"],
                }
            )

        realized = []
        for bucket in realized_by_company.values():
            realized.append(
                {
                    "ticker": bucket["ticker"],
                    "currency": bucket["currency"],
                    "proceeds_native": _money(bucket["proceeds_native"]),
                    "cost_native": _money(bucket["cost_native"]),
                    "gain_native": _money(bucket["gain_native"]),
                    "gain_base": _money(bucket["gain_base"]),
                    "sale_count": bucket["sale_count"],
                    "sales": bucket["sales"],
                }
            )

        total_dividends = sum((Decimal(b["dividends_base"] or 0) for b in dividends), Decimal("0"))
        total_withholding = sum(
            (Decimal(b["withholding_base"] or 0) for b in dividends), Decimal("0")
        )
        total_gain = sum((Decimal(b["gain_base"] or 0) for b in realized), Decimal("0"))

        summary = {
            "fiscal_year": fiscal_year,
            "base_currency": base_currency,
            "total_dividends_base": _money(total_dividends),
            "total_withholding_base": _money(total_withholding),
            "total_realized_gain_base": _money(total_gain),
            "net_taxable_base": _money(total_dividends + total_gain),
            "dividend_count": len(dividends),
            "sell_count": sum(b["sale_count"] for b in realized),
            "method": FIFO_METHOD,
        }

        return {
            "summary": summary,
            "dividends": sorted(dividends, key=lambda d: d["ticker"]),
            "realized": sorted(realized, key=lambda d: d["ticker"]),
            "misc": sorted(misc_rows, key=lambda d: d["date"]),
        }

    def get_or_compute(self, db: Session, fiscal_year: int, regenerate: bool = False) -> dict:
        report = db.scalar(
            select(TaxReport).where(
                TaxReport.fiscal_year == fiscal_year
            ).order_by(TaxReport.updated_at.desc())
        )
        if report is not None and not regenerate:
            return {
                "summary": report.summary,
                "dividends": report.dividends,
                "realized": report.realized,
                "misc": report.misc,
                "generated_at": report.generated_at.isoformat() if report.generated_at else None,
                "persisted": True,
            }

        data = self.compute_report(db, fiscal_year)
        portfolio = self.fx.portfolio(db)
        report = db.scalar(
            select(TaxReport).where(TaxReport.fiscal_year == fiscal_year)
        )
        if report is None:
            report = TaxReport(
                portfolio_id=portfolio.id if portfolio else None,
                fiscal_year=fiscal_year,
                base_currency=data["summary"]["base_currency"],
            )
            db.add(report)
        report.base_currency = data["summary"]["base_currency"]
        report.summary = data["summary"]
        report.dividends = data["dividends"]
        report.realized = data["realized"]
        report.misc = data["misc"]
        report.generated_at = datetime.now(UTC)
        db.commit()
        db.refresh(report)
        data["generated_at"] = report.generated_at.isoformat()
        data["persisted"] = True
        return data

    def _approx_convert(
        self,
        db: Session,
        quote_currency: str,
        base_currency: str,
        as_of: date,
        amount: Decimal,
    ) -> Decimal:
        rate = self.fx.rate(
            db, quote_currency=quote_currency, base_currency=base_currency, as_of=as_of
        )
        if rate is None:
            return amount
        return amount * rate


def build_tax_summary_rows(db: Session, fiscal_year: int) -> list[dict]:
    """Position-derived holdings summary used by the tax page."""
    rows = db.execute(
        select(Position, Company).join(Company, Position.company_id == Company.id)
    ).all()
    result = []
    for position, company in rows:
        result.append(
            {
                "ticker": company.ticker,
                "quantity": float(position.quantity),
                "cost_basis_base": float(position.cost_basis_base or 0),
                "unrealized_pnl_base": float(position.unrealized_pnl_base or 0),
                "as_of": position.as_of.isoformat(),
            }
        )
    return result