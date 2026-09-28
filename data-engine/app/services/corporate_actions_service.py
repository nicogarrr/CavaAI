"""Corporate actions that adjust cost basis and historical quantities.

Splits / reverse splits change share count while preserving the economic
value of a position. To keep the FIFO tax ledger coherent we adjust:

- the open Position (quantity x ratio, average cost / ratio),
- every share-denominated Transaction (buy/sell) strictly before the effective
  date (quantity x ratio, price / ratio) so historical reports and realized
  gains stay correct. Cash movements (dividend, withholding, interest, fee,
  cash_misc) are NEVER rescaled: they store a money amount in ``price``, not a
  per-share price, so dividing them would shrink a EUR 100 dividend to EUR 25
  and the tax report would declare the divided figure.

Ticker changes and mergers update the company identity; merger value
exchange (shares of the acquirer) must be entered as a manual transaction
by the user because it depends on deal terms.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, CorporateAction, Position, Transaction
from app.services.company_resolver import resolve_company


class CorporateActionService:
    def list_actions(self, db: Session, *, limit: int = 500) -> list[CorporateAction]:
        return list(
            db.scalars(
                select(CorporateAction)
                .join(Company, CorporateAction.company_id == Company.id)
                .order_by(CorporateAction.effective_date)
                .limit(limit)
            )
        )

    def create_action(
        self,
        db: Session,
        *,
        ticker: str,
        action_type: str,
        effective_date,
        ratio: Decimal,
        description: str = "",
        apply_now: bool = True,
    ) -> CorporateAction:
        company = resolve_company(db, ticker)
        if company is None:
            raise ValueError(f"Company {ticker} does not exist; import transactions or create it first")
        if ratio <= 0:
            raise ValueError("Ratio must be positive")
        action = CorporateAction(
            company_id=company.id,
            action_type=action_type,
            effective_date=effective_date,
            ratio=ratio,
            description=description,
            applied=False,
        )
        db.add(action)
        db.commit()
        db.refresh(action)
        if apply_now:
            self.apply_action(db, action.id)
        return action

    def delete_action(self, db: Session, action_id: int) -> bool:
        action = db.get(CorporateAction, action_id)
        if action is None:
            return False
        if action.applied:
            raise ValueError(
                "Applied corporate actions are immutable; create a compensating "
                "reverse action instead of deleting"
            )
        db.delete(action)
        db.commit()
        return True

    def apply_action(self, db: Session, action_id: int) -> CorporateAction:
        action = db.get(CorporateAction, action_id)
        if action is None:
            raise ValueError("Corporate action not found")
        if action.applied:
            return action

        ratio = action.ratio
        if ratio <= 0:
            raise ValueError("Ratio must be positive")

        if action.action_type in {"split", "reverse_split"}:
            position = db.scalar(
                select(Position).where(Position.company_id == action.company_id)
            )
            if position is not None:
                position.quantity = (position.quantity * ratio).quantize(Decimal("0.000001"))
                if position.average_cost is not None:
                    position.average_cost = (position.average_cost / ratio).quantize(
                        Decimal("0.000001")
                    )
                if position.market_price is not None:
                    position.market_price = (position.market_price / ratio).quantize(
                        Decimal("0.000001")
                    )
                if position.market_price is not None:
                    position.market_value = position.quantity * position.market_price
                if position.average_cost is not None:
                    position.cost_basis_native = position.quantity * position.average_cost
                # The base-currency columns are left untouched ON PURPOSE: a
                # split preserves money (quantity x price and cost basis are
                # unchanged), so market_value_base, cost_basis_base,
                # unrealized_pnl_base, realized_pnl_base and fx_rate already
                # hold exactly the values a rebuild would write. A
                # PortfolioLedgerService.rebuild_position replay is therefore
                # not run here: it would re-derive the holding from EVERY
                # buy/sell leg (including legs already quoted post-split)
                # instead of rescaling the open position, and it would rewind
                # position.as_of to the last leg's trade date, making a
                # freshly priced position look stale.

            # Share-denominated legs only. Cash rows keep their amount in
            # `price` (quantity 0 or 1 is legitimate for cash, see
            # PortfolioLedgerService and the IBKR importer which writes
            # quantity=1, price=amount): rescaling them would divide a EUR
            # 100 dividend into EUR 25 and a EUR 9.95 commission into EUR
            # 2.49, and the tax report would declare the divided figure.
            transactions = db.scalars(
                select(Transaction).where(
                    Transaction.company_id == action.company_id,
                    Transaction.trade_date < action.effective_date,
                    Transaction.action.in_(("buy", "sell")),
                )
            ).all()
            for transaction in transactions:
                if transaction.quantity is not None:
                    transaction.quantity = (
                        transaction.quantity * ratio
                    ).quantize(Decimal("0.000001"))
                if transaction.price is not None:
                    transaction.price = (transaction.price / ratio).quantize(
                        Decimal("0.000001")
                    )

        elif action.action_type == "ticker_change":
            company = db.get(Company, action.company_id)
            if company is not None and action.description:
                company.name = action.description.split("|")[0].strip() or company.name

        # mergers / spin-offs: deal terms are user-specific; only flag as applied
        # after the user confirms the compensating transactions exist.
        action.applied = True
        action.applied_at = datetime.now(UTC)
        db.commit()
        db.refresh(action)
        return action