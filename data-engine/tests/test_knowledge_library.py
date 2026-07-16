import asyncio
import json
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, select

from app.core.database import SessionLocal, init_db
from app.llm import LLMRequest, LLMResponse, Message, TaskModelRouter, Usage
from app.llm.base import LLMProvider
from app.models import (
    InvestmentPrinciple,
    KnowledgeChunk,
    KnowledgeCollection,
    KnowledgeDocument,
    ProcessingJob,
)
from app.services.knowledge_library_service import (
    DEFAULT_KNOWLEDGE_COLLECTIONS,
    KnowledgeLibraryService,
)


class PrincipleProvider(LLMProvider):
    name = "test"

    def __init__(self, chunk_id: int, fragment: str) -> None:
        super().__init__(
            model_router=TaskModelRouter(default_model="test-model"),
            timeout_seconds=1,
            max_retries=0,
        )
        self.chunk_id = chunk_id
        self.fragment = fragment

    async def complete(self, request: LLMRequest) -> LLMResponse:
        assert request.response_format is not None
        return LLMResponse(
            message=Message(
                "assistant",
                json.dumps(
                    {
                        "principles": [
                            {
                                "principle": "Prefer durable reinvestment runways.",
                                "category": "capital_allocation",
                                "application_conditions": ["high incremental returns"],
                                "exceptions": ["reinvestment destroys value"],
                                "company_tickers": [],
                                "exact_fragment": self.fragment,
                                "chunk_id": self.chunk_id,
                                "confidence": 0.91,
                            }
                        ]
                    }
                ),
            ),
            usage=Usage(input_tokens=10, output_tokens=10, total_tokens=20),
            model="test-model",
            provider=self.name,
        )


def _cleanup(db) -> None:
    db.execute(delete(ProcessingJob))
    db.execute(delete(InvestmentPrinciple))
    db.execute(delete(KnowledgeChunk))
    db.execute(delete(KnowledgeDocument))
    db.execute(delete(KnowledgeCollection))
    db.commit()


def test_knowledge_library_ingestion_deduplication_and_principle_approval():
    init_db()
    db = SessionLocal()
    storage_path: Path | None = None
    try:
        _cleanup(db)
        service = KnowledgeLibraryService()
        collections = service.ensure_default_collections(db)
        assert {item.name for item in collections} == set(DEFAULT_KNOWLEDGE_COLLECTIONS)
        capital_allocation = next(item for item in collections if item.name == "Capital Allocation")

        unique = uuid4().hex
        fragment = "The best businesses can reinvest incremental capital at high rates of return."
        content = f"{fragment} This note is unique to {unique}.".encode()
        result = service.ingest_bytes(
            db,
            title=f"Reinvestment note {unique}",
            content=content,
            filename="reinvestment-note.txt",
            document_type="personal_note",
            collection_id=capital_allocation.id,
            author="CavaAI test",
            language="en",
            content_type="text/plain",
        )
        storage_path = Path(result["storage_uri"])
        assert result["status"] == "ingested"
        assert result["chunks"] == 1

        duplicate = service.ingest_bytes(
            db,
            title="Duplicate",
            content=content,
            filename="duplicate.txt",
            document_type="personal_note",
        )
        assert duplicate["status"] == "duplicate"
        assert duplicate["knowledge_document_id"] == result["knowledge_document_id"]

        document = db.get(KnowledgeDocument, result["knowledge_document_id"])
        assert document is not None
        chunk = db.scalar(
            select(KnowledgeChunk).where(
                KnowledgeChunk.knowledge_document_id == document.id
            )
        )
        assert chunk is not None
        assert chunk.source_locator["knowledge_document_id"] == document.id

        extraction = KnowledgeLibraryService(PrincipleProvider(chunk.id, fragment))
        principles = asyncio.run(extraction.propose_principles(db, document))
        assert len(principles) == 1
        assert principles[0].status == "proposed"
        assert principles[0].exact_fragment == fragment

        approved = extraction.decide_principle(
            db,
            principles[0],
            action="approve",
            actor="owner",
        )
        assert approved.status == "approved"
        assert approved.approved_by == "owner"
        assert approved.approved_at is not None

        duplicate_principles = asyncio.run(extraction.propose_principles(db, document))
        assert duplicate_principles == []
        assert len(db.scalars(select(InvestmentPrinciple)).all()) == 1

        revised = extraction.revise_principle(
            db,
            approved,
            changes={"principle": "Prefer long, durable reinvestment runways."},
            actor="owner",
        )
        assert revised.version == 2
        assert revised.status == "proposed"
        assert revised.canonical_principle_id == approved.id
        assert approved.status == "superseded"
        assert approved.superseded_by_id == revised.id
    finally:
        _cleanup(db)
        db.close()
        if storage_path and storage_path.exists():
            storage_path.unlink()
