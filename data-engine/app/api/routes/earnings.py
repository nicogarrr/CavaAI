from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Company, EarningsRun
from app.schemas import EarningsRunOut, EarningsWorkflowRequest
from app.services.earnings_service import EarningsWorkflowService

router = APIRouter()


@router.post("/{ticker}/run", response_model=EarningsRunOut)
def run_earnings_workflow(
    ticker: str,
    payload: EarningsWorkflowRequest,
    db: Session = Depends(get_db),
) -> EarningsRun:
    company = db.scalar(
        select(Company).where(Company.ticker == ticker.upper())
    )
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    run = EarningsWorkflowService().run(
        db,
        company,
        fiscal_year=payload.fiscal_year,
        fiscal_quarter=payload.fiscal_quarter,
        document_ids=payload.document_ids,
        force_new_thesis=payload.force_new_thesis,
    )
    if run.status == "failed":
        raise HTTPException(
            status_code=422,
            detail={"earnings_run_id": run.id, "error": run.error},
        )
    return run


@router.get("/{ticker}/runs", response_model=list[EarningsRunOut])
def list_earnings_runs(
    ticker: str,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[EarningsRun]:
    company = db.scalar(
        select(Company).where(Company.ticker == ticker.upper())
    )
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return list(
        db.scalars(
            select(EarningsRun)
            .where(EarningsRun.company_id == company.id)
            .order_by(desc(EarningsRun.created_at))
            .limit(limit)
        ).all()
    )
