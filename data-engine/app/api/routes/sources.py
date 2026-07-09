from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Company, Document, DocumentChunk, SourceAudit
from app.services.connectors.quartr import QuartrClient
from app.services.document_ingestion_service import DocumentIngestionService
from app.services.quartr_import_service import QuartrImportService

router = APIRouter()


class QuartrManualImportRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=20)
    title: str = Field(min_length=3, max_length=500)
    text: str = Field(min_length=20)
    source_url: str | None = None
    period: str = "unknown"


class UrlIngestRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=20)
    title: str = Field(min_length=3, max_length=500)
    url: str = Field(min_length=8, max_length=2000)
    source_type: str = Field(default="url", min_length=2, max_length=80)


@router.get("/documents")
def documents(
    ticker: str | None = None,
    include_chunks: bool = False,
    chunk_limit: int = Query(default=1000, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[dict]:
    statement = select(Document, Company).outerjoin(Company, Document.company_id == Company.id)
    if ticker:
        statement = statement.where(Company.ticker == ticker.upper())

    rows = db.execute(statement.order_by(desc(Document.created_at)).limit(200)).all()
    chunk_map: dict[int, list[dict]] = {}
    if include_chunks and rows:
        document_ids = [document.id for document, _ in rows]
        chunks = db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_id.in_(document_ids))
            .order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
            .limit(chunk_limit)
        ).all()
        for chunk in chunks:
            chunk_map.setdefault(chunk.document_id, []).append(
                {
                    "id": chunk.id,
                    "document_id": chunk.document_id,
                    "chunk_index": chunk.chunk_index,
                    "text": chunk.text[:500],
                    "token_count": chunk.token_count,
                    "metadata": chunk.metadata_,
                }
            )

    return [
        {
            "id": document.id,
            "ticker": company.ticker if company else None,
            "title": document.title,
            "source_type": document.source_type,
            "source_url": document.source_url,
            "storage_uri": document.storage_uri,
            "checksum": document.checksum,
            "metadata": document.metadata_,
            "published_at": document.published_at.isoformat() if document.published_at else None,
            "chunks": chunk_map.get(document.id, []) if include_chunks else [],
        }
        for document, company in rows
    ]


@router.post("/documents/ingest-file")
async def ingest_document_file(
    ticker: str = Form(..., min_length=1, max_length=20),
    title: str = Form(..., min_length=3, max_length=500),
    source_type: str = Form(default="manual_upload", min_length=2, max_length=80),
    source_url: str | None = Form(default=None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    try:
        content = await file.read()
        return DocumentIngestionService().ingest_bytes(
            db,
            ticker=ticker,
            title=title,
            content=content,
            filename=file.filename or "upload.bin",
            source_type=source_type,
            source_url=source_url,
            content_type=file.content_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Document ingestion failed: {exc}") from exc


@router.post("/documents/ingest-url")
def ingest_document_url(payload: UrlIngestRequest, db: Session = Depends(get_db)) -> dict:
    try:
        return DocumentIngestionService().ingest_url(
            db,
            ticker=payload.ticker,
            title=payload.title,
            url=payload.url,
            source_type=payload.source_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"URL ingestion failed: {exc}") from exc


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
