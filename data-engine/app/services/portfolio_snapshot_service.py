from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from app.models import (
    CashBalance,
    CashDailySnapshot,
    PortfolioDailySnapshot,
    Position,
    PositionDailySnapshot,
    Transaction,
)
from app.services.portfolio_fx_service import PortfolioFXService


class PortfolioSnapshotService:
    """Persist end-of-day position, cash and valuation inputs for reproducible returns."""

    def __init__(self) -> None:
        self.fx = PortfolioFXService()

    def capture(
        self,
        db: Session,
        *,
        as_of: date | None = None,
        source: str = "market_refresh",
    ) -> PortfolioDailySnapshot:
        snapshot_date = as_of or date.today()
        portfolio = self.fx.ensure_portfolio(db)
        positions = list(
            db.scalars(
                select(Position)
                .where(Position.portfolio_id == portfolio.id)
                .order_by(Position.company_id)
            ).all()
        )
        cash_rows = list(db.scalars(select(CashBalance).order_by(CashBalance.currency)).all())
        existing = db.scalar(
            select(PortfolioDailySnapshot).where(
                PortfolioDailySnapshot.portfolio_id == portfolio.id,
                PortfolioDailySnapshot.snapshot_date == snapshot_date,
            )
        )
        if existing:
            db.execute(
                delete(PositionDailySnapshot).where(
                    PositionDailySnapshot.portfolio_snapshot_id == existing.id
                )
            )
            db.execute(
                delete(CashDailySnapshot).where(
                    CashDailySnapshot.portfolio_snapshot_id == existing.id
                )
            )
            snapshot = existing
        else:
            snapshot = PortfolioDailySnapshot(
                portfolio_id=portfolio.id,
                snapshot_date=snapshot_date,
                base_currency=portfolio.base_currency,
                positions_value_base=Decimal("0"),
                cash_value_base=Decimal("0"),
                total_value_base=Decimal("0"),
                metadata_={},
            )
            db.add(snapshot)
            db.flush()

        position_values: list[tuple[Position, Decimal | None, Decimal | None]] = []
        positions_value = Decimal("0")
        missing_pricing: list[dict[str, Any]] = []
        for position in positions:
            native = position.quantity * position.market_price
            rate = self.fx.rate(
                db,
                quote_currency=position.currency,
                base_currency=portfolio.base_currency,
                as_of=snapshot_date,
            )
            base = native * rate if rate is not None else None
            if base is None or position.as_of != snapshot_date:
                missing_pricing.append(
                    {
                        "company_id": position.company_id,
                        "currency": position.currency,
                        "valuation_date": position.as_of.isoformat(),
                    }
                )
            else:
                positions_value += base
            position_values.append((position, rate, base))

        cash_values: list[tuple[CashBalance, Decimal | None, Decimal | None]] = []
        cash_value = Decimal("0")
        for cash in cash_rows:
            rate = self.fx.rate(
                db,
                quote_currency=cash.currency,
                base_currency=portfolio.base_currency,
                as_of=snapshot_date,
            )
            base = cash.balance * rate if rate is not None else None
            if base is None or cash.as_of != snapshot_date:
                missing_pricing.append(
                    {
                        "cash_currency": cash.currency,
                        "valuation_date": cash.as_of.isoformat(),
                    }
                )
            else:
                cash_value += base
            cash_values.append((cash, rate, base))

        total_value = positions_value + cash_value
        net_flow, ambiguous_flows = self._external_flows(
            db,
            portfolio_id=portfolio.id,
            as_of=snapshot_date,
            base_currency=portfolio.base_currency,
        )
        observations = len(position_values) + len(cash_values)
        pricing_coverage = Decimal(observations - len(missing_pricing)) / Decimal(
            observations or 1
        )
        previous = db.scalar(
            select(PortfolioDailySnapshot)
            .where(
                PortfolioDailySnapshot.portfolio_id == portfolio.id,
                PortfolioDailySnapshot.snapshot_date < snapshot_date,
            )
            .order_by(desc(PortfolioDailySnapshot.snapshot_date))
            .limit(1)
        )
        daily_return: Decimal | None = None
        cumulative_twr: Decimal | None = None
        if (
            previous
            and previous.total_value_base > 0
            and pricing_coverage == Decimal("1")
            and not ambiguous_flows
        ):
            daily_return = (
                total_value - net_flow
            ) / previous.total_value_base - Decimal("1")
            prior_cumulative = previous.cumulative_twr or Decimal("0")
            cumulative_twr = (
                (Decimal("1") + prior_cumulative) * (Decimal("1") + daily_return)
                - Decimal("1")
            )

        snapshot.base_currency = portfolio.base_currency
        snapshot.positions_value_base = positions_value
        snapshot.cash_value_base = cash_value
        snapshot.total_value_base = total_value
        snapshot.net_external_flow_base = net_flow
        snapshot.daily_return = daily_return
        snapshot.cumulative_twr = cumulative_twr
        snapshot.pricing_coverage = pricing_coverage
        snapshot.source = source
        snapshot.metadata_ = {
            "missing_pricing": missing_pricing,
            "ambiguous_external_flows": ambiguous_flows,
            "flow_timing": "end_of_day",
            "position_as_of_dates": sorted(
                {position.as_of.isoformat() for position, _, _ in position_values}
            ),
        }
        db.flush()

        for position, rate, base in position_values:
            db.add(
                PositionDailySnapshot(
                    portfolio_snapshot_id=snapshot.id,
                    portfolio_id=portfolio.id,
                    company_id=position.company_id,
                    snapshot_date=snapshot_date,
                    quantity=position.quantity,
                    market_price_native=position.market_price,
                    currency=position.currency,
                    fx_rate=rate,
                    market_value_native=position.quantity * position.market_price,
                    market_value_base=base,
                    weight=(base / total_value if base is not None and total_value else None),
                    source=source,
                )
            )
        for cash, rate, base in cash_values:
            db.add(
                CashDailySnapshot(
                    portfolio_snapshot_id=snapshot.id,
                    portfolio_id=portfolio.id,
                    snapshot_date=snapshot_date,
                    currency=cash.currency,
                    balance_native=cash.balance,
                    fx_rate=rate,
                    balance_base=base,
                    source=source,
                )
            )
        db.flush()
        return snapshot

    def history(
        self,
        db: Session,
        *,
        start: date | None = None,
        limit: int = 5000,
    ) -> list[PortfolioDailySnapshot]:
        portfolio = self.fx.portfolio(db)
        if portfolio is None:
            return []
        statement = select(PortfolioDailySnapshot).where(
            PortfolioDailySnapshot.portfolio_id == portfolio.id
        )
        if start:
            statement = statement.where(PortfolioDailySnapshot.snapshot_date >= start)
        return list(
            db.scalars(
                statement.order_by(PortfolioDailySnapshot.snapshot_date).limit(limit)
            ).all()
        )

    def _external_flows(
        self,
        db: Session,
        *,
        portfolio_id: int,
        as_of: date,
        base_currency: str,
    ) -> tuple[Decimal, list[int]]:
        transactions = db.scalars(
            select(Transaction).where(
                Transaction.portfolio_id == portfolio_id,
                Transaction.trade_date == as_of,
                Transaction.action.in_(["deposit", "withdrawal", "cash_misc"]),
            )
        ).all()
        total = Decimal("0")
        ambiguous: list[int] = []
        for transaction in transactions:
            if transaction.action == "cash_misc":
                ambiguous.append(transaction.id)
                continue
            rate = self.fx.rate(
                db,
                quote_currency=transaction.currency,
                base_currency=base_currency,
                as_of=as_of,
            )
            if rate is None:
                ambiguous.append(transaction.id)
                continue
            amount = transaction.quantity * transaction.price * rate
            total += amount if transaction.action == "deposit" else -amount
        return total, ambiguous
