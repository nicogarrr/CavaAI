from __future__ import annotations

import hashlib
import os
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.llm import LLMProvider, LLMRequest, Message, ResponseFormat, create_llm_provider
from app.llm.json import parse_json_response
from app.models import (
    Company,
    InvestmentPrinciple,
    KnowledgeChunk,
    KnowledgeCollection,
    KnowledgeDocument,
)
from app.services.document_ingestion_service import (
    MAX_DOCUMENT_BYTES,
    SUPPORTED_EXTENSIONS,
    DocumentIngestionService,
    _extension,
)
from app.services.document_store import DocumentStore


DEFAULT_KNOWLEDGE_COLLECTIONS = (
    "Buffett & Munger",
    "Howard Marks",
    "Fundsmith",
    "Numantia",
    "Capital Allocation",
    "Cyclicals",
    "Compounders",
    "Pre-revenue",
    "Space Industry",
    "Personal Mistakes",
)

KNOWLEDGE_DOCUMENT_TYPES = {
    "fund_letter",
    "book",
    "article",
    "paper",
    "sector_report",
    "personal_note",
    "third_party_thesis",
    "historical_case",
    "personal_postmortem",
}

PRINCIPLE_PROMPT_VERSION = "investment-principles-v1"


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not normalized:
        raise ValueError("Collection name must contain letters or numbers")
    return normalized[:160]


def _compact(value: str) -> str:
    return " ".join(value.lower().split())


class KnowledgeLibraryService:
    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.provider = provider or create_llm_provider()
        self.parser = DocumentIngestionService()

    def ensure_default_collections(self, db: Session) -> list[KnowledgeCollection]:
        existing = {
            collection.slug: collection
            for collection in db.scalars(select(KnowledgeCollection)).all()
        }
        for name in DEFAULT_KNOWLEDGE_COLLECTIONS:
            slug = _slug(name)
            if slug not in existing:
                collection = KnowledgeCollection(
                    name=name,
                    slug=slug,
                    description=f"Canonical CavaAI collection for {name}.",
                    collection_type="system",
                    metadata_={"default": True},
                )
                db.add(collection)
                existing[slug] = collection
        db.commit()
        return list(
            db.scalars(select(KnowledgeCollection).order_by(KnowledgeCollection.name)).all()
        )

    def create_collection(
        self,
        db: Session,
        *,
        name: str,
        description: str = "",
        collection_type: str = "custom",
    ) -> KnowledgeCollection:
        slug = _slug(name)
        if db.scalar(select(KnowledgeCollection).where(KnowledgeCollection.slug == slug)):
            raise ValueError(f"Knowledge collection {name!r} already exists")
        collection = KnowledgeCollection(
            name=name.strip(),
            slug=slug,
            description=description.strip(),
            collection_type=collection_type.strip() or "custom",
            metadata_={},
        )
        db.add(collection)
        db.commit()
        db.refresh(collection)
        return collection

    def ingest_bytes(
        self,
        db: Session,
        *,
        title: str,
        content: bytes,
        filename: str,
        document_type: str,
        collection_id: int | None = None,
        author: str | None = None,
        source_url: str | None = None,
        publication_date: date | None = None,
        language: str = "en",
        content_type: str | None = None,
    ) -> dict[str, Any]:
        if not content:
            raise ValueError("Knowledge document is empty")
        if len(content) > MAX_DOCUMENT_BYTES:
            raise ValueError("Knowledge document exceeds 15MB local ingestion limit")
        if document_type not in KNOWLEDGE_DOCUMENT_TYPES:
            raise ValueError(f"Unsupported knowledge document type: {document_type}")
        collection = db.get(KnowledgeCollection, collection_id) if collection_id else None
        if collection_id and collection is None:
            raise ValueError("Knowledge collection not found")

        checksum = hashlib.sha256(content).hexdigest()
        duplicate = db.scalar(
            select(KnowledgeDocument).where(KnowledgeDocument.checksum == checksum)
        )
        if duplicate:
            return {
                "status": "duplicate",
                "knowledge_document_id": duplicate.id,
                "checksum": checksum,
                "chunks": 0,
            }

        extension = _extension(filename, content_type)
        if extension not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported document extension: {extension}")
        parsed = self.parser._parse(content, filename, extension, content_type)
        if sum(len(block.text.strip()) for block in parsed.blocks) < 20:
            raise ValueError("Knowledge document parser produced too little text")

        storage_uri = DocumentStore().put_bytes(
            "KNOWLEDGE",
            document_type,
            f"{checksum[:12]}-{Path(filename).name}",
            content,
            tenant_id=db.info.get("tenant_id"),
            content_type=content_type or "application/octet-stream",
        )
        document = KnowledgeDocument(
            collection_id=collection.id if collection else None,
            title=title.strip(),
            author=author.strip() if author else None,
            document_type=document_type,
            source_url=source_url,
            storage_uri=storage_uri,
            publication_date=publication_date,
            language=language.strip().lower()[:20] or "en",
            status="ready",
            checksum=checksum,
            metadata_={
                "filename": filename,
                "content_type": content_type,
                "parser": parsed.parser,
                "warnings": parsed.warnings,
                "raw_size_bytes": len(content),
            },
        )
        db.add(document)
        db.flush()

        chunks = self.parser._chunk_blocks(
            parsed.blocks,
            checksum,
            parsed.parser,
            filename,
            source_url,
        )
        for index, payload in enumerate(chunks):
            block_metadata = payload["metadata"].get("block_metadata") or []
            page = next(
                (
                    item.get("page")
                    for item in block_metadata
                    if isinstance(item, dict) and isinstance(item.get("page"), int)
                ),
                None,
            )
            db.add(
                KnowledgeChunk(
                    knowledge_document_id=document.id,
                    chunk_index=index,
                    content=payload["text"],
                    page_number=page,
                    token_count=len(payload["text"].split()),
                    source_locator={
                        "knowledge_document_id": document.id,
                        "chunk_index": index,
                        "page": page,
                        "source_url": source_url,
                    },
                    metadata_=payload["metadata"],
                )
            )
        db.commit()
        db.refresh(document)
        vector_index = {"status": "disabled", "chunks_indexed": 0}
        if os.getenv("CAVAAI_ENABLE_VECTOR_INGEST") == "1":
            from app.services.rag import RAGIndex

            vector_index = {
                "status": "attempted",
                **RAGIndex().ingest_knowledge_document(db, document),
            }
        return {
            "status": "ingested",
            "knowledge_document_id": document.id,
            "collection_id": document.collection_id,
            "checksum": checksum,
            "chunks": len(chunks),
            "parser": parsed.parser,
            "storage_uri": storage_uri,
            "warnings": parsed.warnings,
            "vector_index": vector_index,
        }

    async def propose_principles(
        self,
        db: Session,
        document: KnowledgeDocument,
    ) -> list[InvestmentPrinciple]:
        chunks = list(
            db.scalars(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.knowledge_document_id == document.id)
                .order_by(KnowledgeChunk.chunk_index)
            ).all()
        )
        if not chunks:
            raise ValueError("Knowledge document has no chunks")
        source = "\n\n".join(
            f"[chunk:{chunk.id} page:{chunk.page_number or 'unknown'}]\n{chunk.content}"
            for chunk in chunks
        )
        response = await self.provider.complete(
            LLMRequest(
                messages=[
                    Message(
                        "system",
                        "Extract durable investment principles from the supplied source. "
                        "Every proposal must quote an exact fragment and identify its chunk. "
                        "Do not invent principles that the source does not support.",
                    ),
                    Message("user", source),
                ],
                task="main_financial_analysis",
                temperature=0,
                max_tokens=4000,
                response_format=ResponseFormat.json_schema(
                    self._principle_schema(), name="investment_principles", strict=True
                ),
                metadata={"prompt_version": PRINCIPLE_PROMPT_VERSION},
            )
        )
        payload = parse_json_response(response.text)
        if not isinstance(payload, dict) or not isinstance(payload.get("principles"), list):
            raise ValueError("Invalid investment principle extraction response")

        chunks_by_id = {chunk.id: chunk for chunk in chunks}
        companies = {
            company.ticker.upper(): company.id for company in db.scalars(select(Company)).all()
        }
        created: list[InvestmentPrinciple] = []
        for item in payload["principles"]:
            if not isinstance(item, dict):
                continue
            chunk_id = self._integer(item.get("chunk_id"))
            chunk = chunks_by_id.get(chunk_id) if chunk_id is not None else None
            fragment = str(item.get("exact_fragment") or "").strip()
            if chunk is None or not fragment or _compact(fragment) not in _compact(chunk.content):
                continue
            confidence = max(0.0, min(1.0, float(item.get("confidence") or 0)))
            principle = InvestmentPrinciple(
                knowledge_document_id=document.id,
                knowledge_chunk_id=chunk.id,
                collection_id=document.collection_id,
                principle=str(item.get("principle") or "").strip(),
                category=str(item.get("category") or "general")[:120],
                application_conditions=self._strings(item.get("application_conditions")),
                exceptions=self._strings(item.get("exceptions")),
                applies_to_company_ids=[
                    companies[ticker.upper()]
                    for ticker in self._strings(item.get("company_tickers"))
                    if ticker.upper() in companies
                ],
                exact_fragment=fragment,
                page_number=chunk.page_number,
                author=document.author,
                confidence=Decimal(str(confidence)),
                status="proposed",
                metadata_={
                    "model": response.model,
                    "provider": response.provider,
                    "request_id": response.request_id,
                    "prompt_version": PRINCIPLE_PROMPT_VERSION,
                },
            )
            if principle.principle:
                db.add(principle)
                created.append(principle)
        db.commit()
        for principle in created:
            db.refresh(principle)
        return created

    def decide_principle(
        self,
        db: Session,
        principle: InvestmentPrinciple,
        *,
        action: str,
        actor: str,
    ) -> InvestmentPrinciple:
        if principle.status != "proposed":
            raise ValueError("Only proposed principles can be approved or rejected")
        if action not in {"approve", "reject"}:
            raise ValueError("Principle action must be approve or reject")
        principle.status = "approved" if action == "approve" else "rejected"
        principle.approved_by = actor
        principle.approved_at = datetime.now(UTC)
        db.commit()
        db.refresh(principle)
        return principle

    @staticmethod
    def list_documents(db: Session, *, collection_id: int | None = None) -> list[dict]:
        statement = select(KnowledgeDocument).order_by(desc(KnowledgeDocument.created_at))
        if collection_id is not None:
            statement = statement.where(KnowledgeDocument.collection_id == collection_id)
        return [
            {
                "id": document.id,
                "collection_id": document.collection_id,
                "title": document.title,
                "author": document.author,
                "document_type": document.document_type,
                "source_url": document.source_url,
                "publication_date": document.publication_date,
                "language": document.language,
                "status": document.status,
                "checksum": document.checksum,
                "metadata": document.metadata_,
                "created_at": document.created_at,
            }
            for document in db.scalars(statement).all()
        ]

    @staticmethod
    def _strings(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    @staticmethod
    def _integer(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _principle_schema() -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "principles": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "principle": {"type": "string"},
                            "category": {"type": "string"},
                            "application_conditions": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "exceptions": {"type": "array", "items": {"type": "string"}},
                            "company_tickers": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "exact_fragment": {"type": "string"},
                            "chunk_id": {"type": "integer"},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        },
                        "required": [
                            "principle",
                            "category",
                            "application_conditions",
                            "exceptions",
                            "company_tickers",
                            "exact_fragment",
                            "chunk_id",
                            "confidence",
                        ],
                    },
                }
            },
            "required": ["principles"],
        }
