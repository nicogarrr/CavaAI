from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Company, FinancialFact
from app.schemas import CompanyOut, FinancialFactOut, FinancialRefreshResponse
from app.services.connectors.fmp import FMPClient
from app.services.financial_ingestion_service import FinancialIngestionService

router = APIRouter()


@router.get("", response_model=list[CompanyOut])
def list_companies(db: Session = Depends(get_db)) -> list[Company]:
    return list(db.scalars(select(Company).order_by(Company.ticker)).all())


@router.get("/{ticker}", response_model=CompanyOut)
def get_company(ticker: str, db: Session = Depends(get_db)) -> Company:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


@router.get("/{ticker}/facts", response_model=list[FinancialFactOut])
def list_financial_facts(
    ticker: str,
    metric: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[FinancialFact]:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    query = select(FinancialFact).where(FinancialFact.company_id == company.id)
    if metric:
        query = query.where(FinancialFact.metric == metric)
    query = query.order_by(
        FinancialFact.fiscal_year.desc().nullslast(),
        desc(FinancialFact.created_at),
    ).limit(limit)
    return list(db.scalars(query).all())


@router.post("/{ticker}/refresh/fmp", response_model=FinancialRefreshResponse)
async def refresh_fmp_financials(ticker: str, db: Session = Depends(get_db)) -> dict:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    try:
        return await FinancialIngestionService().refresh_from_fmp(
            db=db,
            company=company,
            client=FMPClient(),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=424, detail=str(exc)) from exc


@router.post("/{ticker}/refresh/sec", response_model=FinancialRefreshResponse)
async def refresh_sec_financials(ticker: str, db: Session = Depends(get_db)) -> dict:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        return await FinancialIngestionService().refresh_from_sec(db=db, company=company)
    except RuntimeError as exc:
        raise HTTPException(status_code=424, detail=str(exc)) from exc
