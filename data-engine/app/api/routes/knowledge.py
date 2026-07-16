from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import (
    InvestmentPrinciple,
    KnowledgeChunk,
    KnowledgeCollection,
    KnowledgeDocument,
    ProcessingJob,
)
from app.services.knowledge_library_service import KnowledgeLibraryService


router = APIRouter()


class CollectionCreate(BaseModel):
    name: str = Field(min_length=2, max_length=240)
    description: str = Field(default="", max_length=4000)
    collection_type: str = Field(default="custom", min_length=2, max_length=80)


class PrincipleAction(BaseModel):
    action: str = Field(pattern="^(approve|reject|merge)$")
    actor: str = Field(default="user", min_length=1, max_length=160)
    canonical_principle_id: int | None = Field(default=None, ge=1)


class PrincipleRevision(BaseModel):
    principle: str | None = Field(default=None, min_length=3)
    category: str | None = Field(default=None, min_length=1, max_length=120)
    application_conditions: list[str] | None = None
    exceptions: list[str] | None = None
    applies_to_company_ids: list[int] | None = None
    exact_fragment: str | None = Field(default=None, min_length=1)
    page_number: int | None = Field(default=None, ge=1)
    author: str | None = Field(default=None, max_length=240)
    confidence: float | None = Field(default=None, ge=0, le=1)
    actor: str = Field(default="user", min_length=1, max_length=160)


def _collection(collection: KnowledgeCollection) -> dict:
    return {
        "id": collection.id,
        "name": collection.name,
        "slug": collection.slug,
        "description": collection.description,
        "collection_type": collection.collection_type,
        "metadata": collection.metadata_,
    }


def _principle(principle: InvestmentPrinciple) -> dict:
    return {
        "id": principle.id,
        "knowledge_document_id": principle.knowledge_document_id,
        "knowledge_chunk_id": principle.knowledge_chunk_id,
        "collection_id": principle.collection_id,
        "principle": principle.principle,
        "principle_fingerprint": principle.principle_fingerprint,
        "semantic_duplicate_of_id": principle.semantic_duplicate_of_id,
        "canonical_principle_id": principle.canonical_principle_id,
        "version": principle.version,
        "superseded_by_id": principle.superseded_by_id,
        "category": principle.category,
        "application_conditions": principle.application_conditions,
        "exceptions": principle.exceptions,
        "applies_to_company_ids": principle.applies_to_company_ids,
        "exact_fragment": principle.exact_fragment,
        "page_number": principle.page_number,
        "author": principle.author,
        "confidence": principle.confidence,
        "status": principle.status,
        "approved_by": principle.approved_by,
        "approved_at": principle.approved_at,
        "metadata": principle.metadata_,
    }


def _job(job: ProcessingJob) -> dict:
    return {
        "id": job.id,
        "job_type": job.job_type,
        "entity_type": job.entity_type,
        "entity_id": job.entity_id,
        "status": job.status,
        "progress_current": job.progress_current,
        "progress_total": job.progress_total,
        "result": job.result,
        "error": job.error,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


@router.post("/collections/defaults")
def install_default_collections(db: Session = Depends(get_db)) -> list[dict]:
    return [
        _collection(collection)
        for collection in KnowledgeLibraryService().ensure_default_collections(db)
    ]


@router.get("/collections")
def list_collections(db: Session = Depends(get_db)) -> list[dict]:
    return [
        _collection(collection)
        for collection in db.scalars(
            select(KnowledgeCollection).order_by(KnowledgeCollection.name)
        ).all()
    ]


@router.post("/collections")
def create_collection(payload: CollectionCreate, db: Session = Depends(get_db)) -> dict:
    try:
        return _collection(
            KnowledgeLibraryService().create_collection(
                db,
                name=payload.name,
                description=payload.description,
                collection_type=payload.collection_type,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/documents")
def list_documents(
    collection_id: int | None = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    return KnowledgeLibraryService.list_documents(db, collection_id=collection_id)


@router.post("/documents/upload")
async def upload_document(
    title: str = Form(..., min_length=2, max_length=500),
    document_type: str = Form(...),
    collection_id: int | None = Form(default=None),
    author: str | None = Form(default=None, max_length=240),
    source_url: str | None = Form(default=None),
    publication_date: date | None = Form(default=None),
    language: str = Form(default="en", max_length=20),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return KnowledgeLibraryService().ingest_bytes(
            db,
            title=title,
            document_type=document_type,
            collection_id=collection_id,
            author=author,
            source_url=source_url,
            publication_date=publication_date,
            language=language,
            content=await file.read(),
            filename=file.filename or "knowledge-document.bin",
            content_type=file.content_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Knowledge ingestion failed: {exc}") from exc


@router.get("/documents/{document_id}/chunks")
def document_chunks(
    document_id: int,
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[dict]:
    if db.get(KnowledgeDocument, document_id) is None:
        raise HTTPException(status_code=404, detail="Knowledge document not found")
    return [
        {
            "id": chunk.id,
            "knowledge_document_id": chunk.knowledge_document_id,
            "chunk_index": chunk.chunk_index,
            "content": chunk.content,
            "page_number": chunk.page_number,
            "section_title": chunk.section_title,
            "token_count": chunk.token_count,
            "source_locator": chunk.source_locator,
            "metadata": chunk.metadata_,
        }
        for chunk in db.scalars(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.knowledge_document_id == document_id)
            .order_by(KnowledgeChunk.chunk_index)
            .limit(limit)
        ).all()
    ]


@router.post("/documents/{document_id}/extract-principles")
def extract_principles(
    document_id: int,
    db: Session = Depends(get_db),
) -> dict:
    document = db.get(KnowledgeDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Knowledge document not found")
    active = db.scalar(
        select(ProcessingJob)
        .where(
            ProcessingJob.job_type == "knowledge_principle_extraction",
            ProcessingJob.entity_type == "knowledge_document",
            ProcessingJob.entity_id == document_id,
            ProcessingJob.status.in_(["queued", "running"]),
        )
        .order_by(desc(ProcessingJob.created_at))
    )
    if active:
        return _job(active)
    job = ProcessingJob(
        job_type="knowledge_principle_extraction",
        entity_type="knowledge_document",
        entity_id=document.id,
        status="queued",
        result={},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    try:
        from app.workers.dramatiq_app import extract_knowledge_principles

        message = extract_knowledge_principles.send(
            job.id,
            tenant_id=db.info.get("tenant_id"),
            user_id=db.info.get("user_id"),
        )
        job.result = {"broker_message_id": str(message.message_id)}
        db.commit()
        db.refresh(job)
        return _job(job)
    except Exception as exc:
        job.status = "failed"
        job.error = f"Queue dispatch failed: {exc}"
        db.commit()
        raise HTTPException(
            status_code=503,
            detail={"message": "Principle extraction queue is unavailable", "job_id": job.id},
        ) from exc


@router.get("/jobs")
def list_jobs(
    document_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict]:
    statement = select(ProcessingJob).where(
        ProcessingJob.job_type == "knowledge_principle_extraction"
    )
    if document_id is not None:
        statement = statement.where(ProcessingJob.entity_id == document_id)
    return [
        _job(job)
        for job in db.scalars(
            statement.order_by(desc(ProcessingJob.created_at)).limit(limit)
        ).all()
    ]


@router.get("/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)) -> dict:
    job = db.get(ProcessingJob, job_id)
    if job is None or job.job_type != "knowledge_principle_extraction":
        raise HTTPException(status_code=404, detail="Processing job not found")
    return _job(job)


@router.get("/principles")
def list_principles(
    status: str | None = Query(default=None),
    collection_id: int | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[dict]:
    statement = select(InvestmentPrinciple)
    if status:
        statement = statement.where(InvestmentPrinciple.status == status)
    if collection_id is not None:
        statement = statement.where(InvestmentPrinciple.collection_id == collection_id)
    return [
        _principle(principle)
        for principle in db.scalars(
            statement.order_by(desc(InvestmentPrinciple.created_at)).limit(limit)
        ).all()
    ]


@router.post("/principles/{principle_id}/action")
def action_principle(
    principle_id: int,
    payload: PrincipleAction,
    db: Session = Depends(get_db),
) -> dict:
    principle = db.get(InvestmentPrinciple, principle_id)
    if principle is None:
        raise HTTPException(status_code=404, detail="Investment principle not found")
    try:
        if payload.action == "merge":
            canonical = db.get(InvestmentPrinciple, payload.canonical_principle_id)
            if canonical is None:
                raise ValueError("Canonical principle was not found")
            return _principle(
                KnowledgeLibraryService().merge_principle(
                    db,
                    principle,
                    canonical=canonical,
                    actor=payload.actor,
                )
            )
        return _principle(
            KnowledgeLibraryService().decide_principle(
                db,
                principle,
                action=payload.action,
                actor=payload.actor,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.put("/principles/{principle_id}")
def revise_principle(
    principle_id: int,
    payload: PrincipleRevision,
    db: Session = Depends(get_db),
) -> dict:
    principle = db.get(InvestmentPrinciple, principle_id)
    if principle is None:
        raise HTTPException(status_code=404, detail="Investment principle not found")
    changes = payload.model_dump(exclude={"actor"}, exclude_none=True)
    if not changes:
        raise HTTPException(status_code=400, detail="At least one revision field is required")
    try:
        return _principle(
            KnowledgeLibraryService().revise_principle(
                db,
                principle,
                changes=changes,
                actor=payload.actor,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
