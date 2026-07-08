from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import CashBalance, Company, Position
from app.services.risk_service import RiskService

router = APIRouter()


@router.get("/summary")
def portfolio_summary(db: Session = Depends(get_db)) -> dict:
    risk = RiskService().dashboard(db)
    return {
        "total_value": risk["total_value"],
        "equity_value": risk["equity_value"],
        "cash": risk["cash"],
        "top_1_weight": risk["top_1_weight"],
        "top_5_weight": risk["top_5_weight"],
        "alerts": risk["alerts"],
    }


@router.get("/positions")
def positions(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(select(Position, Company).join(Company, Position.company_id == Company.id)).all()
    return [
        {
            "ticker": company.ticker,
            "name": company.name,
            "sector": company.sector,
            "quantity": float(position.quantity),
            "market_price": float(position.market_price),
            "market_value": float(position.market_value),
            "unrealized_pnl": float(position.unrealized_pnl),
            "currency": position.currency,
            "source": position.source,
        }
        for position, company in rows
    ]


@router.get("/cash")
def cash(db: Session = Depends(get_db)) -> list[dict]:
    return [
        {
            "currency": row.currency,
            "balance": float(row.balance),
            "settled_cash": float(row.settled_cash),
            "interest_rate": float(row.interest_rate),
            "source": row.source,
        }
        for row in db.scalars(select(CashBalance)).all()
    ]


@router.post("/import/ibkr")
def import_ibkr() -> dict:
    return {
        "status": "not_configured",
        "message": "Set IBKR_FLEX_TOKEN and IBKR_FLEX_QUERY_ID, then run the IBKR Flex connector.",
    }

