from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Company, ThesisVersion
from app.schemas import ThesisGenerateRequest, ThesisOut
from app.services.thesis_service import ThesisService

router = APIRouter()


@router.post("/generate", response_model=ThesisOut)
def generate_thesis(payload: ThesisGenerateRequest, db: Session = Depends(get_db)) -> ThesisVersion:
    try:
        return ThesisService().generate(db, payload.ticker, payload.force_new_version)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{ticker}/latest", response_model=ThesisOut)
def latest_thesis(ticker: str, db: Session = Depends(get_db)) -> ThesisVersion:
    thesis = ThesisService().latest(db, ticker)
    if not thesis:
        raise HTTPException(status_code=404, detail="No thesis for ticker")
    return thesis


@router.get("/{ticker}/versions", response_model=list[ThesisOut])
def thesis_versions(ticker: str, db: Session = Depends(get_db)) -> list[ThesisVersion]:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return list(
        db.scalars(
            select(ThesisVersion)
            .where(ThesisVersion.company_id == company.id)
            .order_by(desc(ThesisVersion.version))
        ).all()
    )

