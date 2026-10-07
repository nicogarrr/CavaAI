"""Authenticated data inventory and public short-position snapshots."""
from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Company
from app.services.data_health_service import read_inventory
from app.services.short_positions_service import read_shorts, refresh_shorts

router = APIRouter()


@router.get("")
def data_health(db: Session = Depends(get_db)) -> dict:
    return read_inventory(db)


def _company(db: Session, ticker: str) -> Company:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if company is None:
        raise HTTPException(status_code=404, detail="Empresa no registrada")
    return company


@router.get("/shorts/{ticker}")
def shorts(ticker: str = Path(min_length=1, max_length=20), db: Session = Depends(get_db)) -> dict:
    return read_shorts(db, _company(db, ticker))


@router.post("/shorts/{ticker}/refresh")
async def shorts_refresh(ticker: str = Path(min_length=1, max_length=20), db: Session = Depends(get_db)) -> dict:
    return await refresh_shorts(db, _company(db, ticker))
