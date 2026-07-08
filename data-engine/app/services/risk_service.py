from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CashBalance, Company, Position
from app.valuation import calculate_portfolio_risk


class RiskService:
    def dashboard(self, db: Session) -> dict:
        rows = db.execute(select(Position, Company).join(Company, Position.company_id == Company.id)).all()
        positions = [
            {
                "ticker": company.ticker,
                "name": company.name,
                "sector": company.sector,
                "factor_tags": company.factor_tags,
                "market_value": position.market_value,
                "market_price": position.market_price,
                "unrealized_pnl": position.unrealized_pnl,
            }
            for position, company in rows
        ]
        cash = [
            {"currency": row.currency, "balance": row.balance}
            for row in db.scalars(select(CashBalance)).all()
        ]
        return calculate_portfolio_risk(positions, cash)

