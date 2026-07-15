from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CashBalance, Company, Position
from app.services.portfolio_fx_service import PortfolioFXService
from app.valuation import calculate_portfolio_risk


class RiskService:
    def dashboard(self, db: Session) -> dict:
        fx = PortfolioFXService()
        base_currency = fx.base_currency(db)
        missing_fx: list[dict] = []
        rows = db.execute(select(Position, Company).join(Company, Position.company_id == Company.id)).all()
        positions = []
        for position, company in rows:
            value_base = position.market_value_base
            if value_base is None and position.currency == base_currency:
                value_base = position.market_value_native or position.market_value
            if value_base is None:
                missing_fx.append(
                    {
                        "kind": "position",
                        "ticker": company.ticker,
                        "quote_currency": position.currency,
                        "base_currency": base_currency,
                        "as_of": position.as_of.isoformat(),
                    }
                )
                continue
            positions.append({
                "ticker": company.ticker,
                "name": company.name,
                "sector": company.sector,
                "factor_tags": company.factor_tags,
                "market_value": value_base,
                "market_price": position.market_price,
                "unrealized_pnl": position.unrealized_pnl_base,
            })
        cash_native: dict[str, float] = {}
        cash_base = 0.0
        for row in db.scalars(select(CashBalance)).all():
            cash_native[row.currency] = cash_native.get(row.currency, 0.0) + float(row.balance)
            rate = fx.rate(
                db,
                quote_currency=row.currency,
                base_currency=base_currency,
                as_of=row.as_of,
            )
            if rate is None:
                missing_fx.append(
                    {
                        "kind": "cash",
                        "quote_currency": row.currency,
                        "base_currency": base_currency,
                        "as_of": row.as_of.isoformat(),
                    }
                )
                continue
            cash_base += float(row.balance * rate)
        result = calculate_portfolio_risk(
            positions,
            [{"currency": base_currency, "balance": cash_base}],
        )
        result.update(
            {
                "status": "incomplete_fx" if missing_fx else "ok",
                "base_currency": base_currency,
                "cash_native": cash_native,
                "missing_fx": missing_fx,
            }
        )
        result["trace"] = {
            "method": "portfolio_risk_snapshot_fx_v2",
            "fx_policy": "quote amount multiplied by latest rate on or before as_of",
            "excluded_for_missing_fx": len(missing_fx),
        }
        return result
