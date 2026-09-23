from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.connectors import short_interest
from app.services.risk_service import RiskService

router = APIRouter()


@router.get("/dashboard")
def risk_dashboard(db: Session = Depends(get_db)) -> dict:
    return RiskService().dashboard(db)


async def market_stress_signals(ticker: str | None = None) -> dict:
    """Senales de estres de mercado (VIX + posicion corta FINRA).

    El conector degrada a ``unavailable`` cuando los vendors gratuitos no
    responden; nunca se fabrican senales.
    """
    return await short_interest.market_stress_report(ticker)


@router.get("/market-stress")
async def market_stress(ticker: str | None = None) -> dict:
    return await market_stress_signals(ticker)
