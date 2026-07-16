from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.llm.errors import LLMError
from app.models import InvestmentPrinciple, KnowledgeChunk, KnowledgeCollection, KnowledgeDocument
from app.services.knowledge_library_service import KnowledgeLibraryService


router = APIRouter()


class CollectionCreate(BaseModel):
    name: str = Field(min_length=2, max_length=240)
    description: str = Field(default="", max_length=4000)
    collection_type: str = Field(default="custom", min_length=2, max_length=80)


class PrincipleAction(BaseModel):
    action: str = Field(pattern="^(approve|reject)$")
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
async def extract_principles(
    document_id: int,
    db: Session = Depends(get_db),
) -> list[dict]:
    document = db.get(KnowledgeDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Knowledge document not found")
    try:
        return [
            _principle(principle)
            for principle in await KnowledgeLibraryService().propose_principles(db, document)
        ]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


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
