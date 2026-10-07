"""Library doctrine with SQL-backed, tenant-scoped citation identity.

Retrieved letters are context for inference, never company financial facts.
Vector payload text, titles and URLs are not authoritative.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KnowledgeChunk, KnowledgeDocument
from app.services.rag import RAGIndex


def retrieve_library_context(db: Session, question: str, limit: int = 3) -> list[dict]:
    tenant_id = db.info.get("tenant_id")
    if type(tenant_id) is not int or tenant_id <= 0:
        return []
    try:
        hits = RAGIndex().search(question, ticker=None, limit=20, tenant_id=tenant_id)
    except Exception:
        return []
    contexts = []
    seen = set()
    for hit in hits:
        chunk_id = hit.get("entity_id")
        if hit.get("entity_type") != "knowledge_chunk" or type(chunk_id) is not int or chunk_id in seen:
            continue
        row = db.execute(
            select(KnowledgeChunk, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.knowledge_document_id)
            .where(KnowledgeChunk.id == chunk_id, KnowledgeChunk.tenant_id == tenant_id,
                   KnowledgeDocument.tenant_id == tenant_id, KnowledgeDocument.status == "ready")
        ).first()
        if not row:
            continue
        chunk, document = row
        if not chunk.content.strip() or not chunk.qdrant_point_id or str(hit.get("point_id")) != chunk.qdrant_point_id:
            continue
        seen.add(chunk_id)
        contexts.append({
            "type": "knowledge_chunk", "id": chunk.id, "chunk_id": chunk.id,
            "knowledge_document_id": document.id, "title": document.title,
            "author": document.author, "url": document.source_url,
            "source_type": document.document_type, "page_number": chunk.page_number,
            "chunk_index": chunk.chunk_index, "text": chunk.content[:1600],
            "evidence_role": "investment_doctrine_not_company_fact",
        })
        if len(contexts) >= limit:
            break
    return contexts
