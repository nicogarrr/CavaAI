from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.risk_service import RiskService

router = APIRouter()


@router.get("/dashboard")
def risk_dashboard(db: Session = Depends(get_db)) -> dict:
    return RiskService().dashboard(db)

