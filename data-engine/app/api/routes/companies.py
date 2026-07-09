from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Company, FinancialFact
from app.schemas import CalculatedMetricOut, CalculatedMetricsResponse, CompanyOut, FinancialFactOut, FinancialRefreshResponse
from app.services.connectors.fmp import FMPClient
from app.services.financial_ingestion_service import FinancialIngestionService
from app.services.metric_calculation_service import MetricCalculationService
from app.services.peer_comparison_service import DEFAULT_PEER_METRICS, PeerComparisonService

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


@router.get("/{ticker}/metrics/calculated", response_model=CalculatedMetricsResponse)
def list_calculated_metrics(
    ticker: str,
    refresh: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> dict:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    service = MetricCalculationService()
    metrics = service.calculate_all(db, company, persist=refresh)
    return {
        "ticker": company.ticker,
        "status": "calculated",
        "metrics": [
            CalculatedMetricOut(
                id=result.id,
                company_id=company.id,
                metric=result.metric,
                value=result.value,
                unit=result.unit,
                period=result.period,
                fiscal_year=result.fiscal_year,
                fiscal_quarter=result.fiscal_quarter,
                status=result.status,
                definition_version=result.definition_version,
                formula=result.formula,
                numerator=result.numerator,
                denominator=result.denominator,
                source_fact_ids=result.source_fact_ids,
                calculation_trace=result.calculation_trace,
                confidence=result.confidence,
            )
            for result in metrics
        ],
    }


@router.get("/{ticker}/peers/comparison")
def peer_comparison(
    ticker: str,
    limit: int = Query(default=8, ge=1, le=20),
    refresh: bool = Query(default=False),
    metrics: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    metric_names = [item.strip() for item in metrics.split(",") if item.strip()] if metrics else DEFAULT_PEER_METRICS
    return PeerComparisonService().compare(
        db,
        company,
        limit=limit,
        metrics=metric_names,
        refresh=refresh,
    )


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
