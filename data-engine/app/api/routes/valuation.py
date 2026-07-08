from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Company
from app.schemas import ValuationResponse
from app.services.valuation_service import ValuationService

router = APIRouter()


@router.get("/{ticker}", response_model=ValuationResponse)
def valuation(ticker: str, db: Session = Depends(get_db)) -> dict:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return ValuationService().value_company(db, company)

