from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Company, Document, SourceAudit
from app.services.connectors.quartr import QuartrClient
from app.services.quartr_import_service import QuartrImportService

router = APIRouter()


class QuartrManualImportRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=20)
    title: str = Field(min_length=3, max_length=500)
    text: str = Field(min_length=20)
    source_url: str | None = None
    period: str = "unknown"


@router.get("/documents")
def documents(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        select(Document, Company)
        .outerjoin(Company, Document.company_id == Company.id)
        .order_by(desc(Document.created_at))
        .limit(200)
    ).all()
    return [
        {
            "id": document.id,
            "ticker": company.ticker if company else None,
            "title": document.title,
            "source_type": document.source_type,
            "source_url": document.source_url,
            "published_at": document.published_at.isoformat() if document.published_at else None,
        }
        for document, company in rows
    ]


@router.get("/audits")
def source_audits(db: Session = Depends(get_db)) -> list[dict]:
    return [
        {
            "id": audit.id,
            "thesis_version_id": audit.thesis_version_id,
            "passed": audit.passed,
            "source_coverage_score": audit.source_coverage_score,
            "unsupported_claims": audit.unsupported_claims,
            "weak_claims": audit.weak_claims,
            "data_conflicts": audit.data_conflicts,
            "required_fixes": audit.required_fixes,
        }
        for audit in db.scalars(select(SourceAudit).order_by(desc(SourceAudit.created_at))).all()
    ]


@router.get("/quartr/status")
def quartr_status() -> dict:
    configured = QuartrClient().configured()
    return {
        "api_configured": configured,
        "free_student_mode": "manual_import",
        "message": (
            "Use manual import for Quartr Student/Free. Set QUARTR_API_KEY only if Quartr "
            "has issued enterprise/API credentials."
        ),
    }


@router.post("/quartr/import-text")
def import_quartr_text(
    payload: QuartrManualImportRequest,
    db: Session = Depends(get_db),
) -> dict:
    try:
        return QuartrImportService().import_text(
            db=db,
            ticker=payload.ticker,
            title=payload.title,
            text=payload.text,
            source_url=payload.source_url,
            period=payload.period,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
