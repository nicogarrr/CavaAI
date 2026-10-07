"""Tenant-scoped retrieved excerpts with PostgreSQL-backed citation identity."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, Document, DocumentChunk
from app.services.library_context import retrieve_library_context
from app.services.rag import RAGIndex


def retrieve_thesis_context(db: Session, company: Company) -> list[dict]:
    tenant_id = db.info.get("tenant_id")
    if tenant_id is None:
        return []
    try:
        hits = RAGIndex().search(
            f"{company.ticker} business risks financial results regulatory filings",
            ticker=company.ticker, limit=5, tenant_id=tenant_id,
        )
    except Exception:
        return []
    contexts = []
    seen = set()
    for hit in hits:
        if hit.get("entity_type") != "document_chunk":
            continue
        chunk_id = hit.get("entity_id")
        if not isinstance(chunk_id, int) or chunk_id in seen:
            continue
        row = db.execute(
            select(DocumentChunk, Document)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                DocumentChunk.id == chunk_id,
                DocumentChunk.tenant_id == tenant_id,
                Document.tenant_id == tenant_id,
                Document.company_id == company.id,
            )
        ).first()
        if not row:
            continue
        chunk, document = row
        if not chunk.text.strip():
            continue
        seen.add(chunk_id)
        contexts.append({
            "text": chunk.text[:1600], "title": document.title,
            "source_type": document.source_type, "url": document.source_url,
            "document_id": document.id, "chunk_id": chunk.id,
            "chunk_index": chunk.chunk_index,
        })
    return contexts + retrieve_library_context(
        db, f"{company.ticker} investment principles capital allocation business risks"
    )
