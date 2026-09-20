"""Circuito RAG end-to-end contra Qdrant real.

Requiere Qdrant en localhost:6333 (``docker compose up -d qdrant``).
Sin Qdrant los tests se skipean; con Qdrant usan embeddings locales
(all-MiniLM-L6-v2, primera ejecucion descarga el modelo) y BD sqlite
en memoria, sin tocar Postgres ni MinIO.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import Company, DocumentChunk, Tenant

COLLECTION = "portfolio_research_documents"
SOURCE_TYPE = "rag_activation_test"


def _qdrant_reachable() -> bool:
    try:
        from app.services.rag import RAGIndex

        return bool(RAGIndex().status().get("configured"))
    except Exception:
        return False


requires_qdrant = pytest.mark.skipif(
    not _qdrant_reachable(),
    reason="Qdrant no disponible en localhost:6333 (docker compose up -d qdrant)",
)


def _session_with_tenant() -> tuple[Session, int, str]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    token = uuid4().hex[:12]
    tenant = Tenant(external_id=f"rag-activation-{token}", name="RAG activation")
    db.add(tenant)
    db.flush()
    db.info["tenant_id"] = tenant.id
    ticker = f"RAGT{token[:4]}".upper()
    db.add(
        Company(
            ticker=ticker,
            name="RAG Activation Co",
            exchange="TEST",
            currency="USD",
            sector="Technology",
            industry="Software",
            company_type="standard",
            valuation_model="standard_dcf",
            special_sources=[],
            special_risks=[],
            factor_tags=[],
        )
    )
    db.flush()
    return db, tenant.id, ticker


def _probe_text(token: str) -> str:
    return (
        f"# RAG activation note {token}\n\n"
        f"Operating margin discipline {token} and Azure AI demand are key thesis "
        "evidence. This note validates the vector circuit: local embeddings, "
        "Qdrant storage, and tenant-scoped semantic retrieval.\n\n"
        f"Cloud growth re-accelerates while cost discipline protects margins {token}. "
        "Capital allocation prioritizes accelerators and shareholder returns.\n"
    )


@pytest.fixture()
def tenant_db(monkeypatch):
    monkeypatch.setenv("CAVAAI_ENABLE_VECTOR_INGEST", "1")
    monkeypatch.setenv("CAVAAI_ENABLE_VECTOR_SEARCH", "1")
    monkeypatch.setenv("CAVAAI_ENABLE_AUTO_KPI_EXTRACTION", "0")
    monkeypatch.setenv("CAVAAI_ENABLE_AUTO_RESEARCH", "0")
    db, tenant_id, ticker = _session_with_tenant()
    yield db, tenant_id, ticker
    # Limpieza: puntos de Qdrant creados por el test (por ID exacto).
    try:
        from app.services.rag import RAGIndex

        point_ids = [
            chunk.qdrant_point_id
            for chunk in db.scalars(select(DocumentChunk)).all()
            if chunk.qdrant_point_id
        ]
        if point_ids:
            RAGIndex().client().delete(
                collection_name=COLLECTION, points_selector=point_ids, wait=True
            )
    except Exception:
        pass
    raw_root = Path(f"storage/raw/{ticker}/{SOURCE_TYPE}")
    if raw_root.exists():
        for path in raw_root.glob("*"):
            if path.is_file():
                path.unlink()
    db.close()


@requires_qdrant
def test_ingest_indexes_vectors_in_qdrant(tenant_db):
    from app.services.rag import RAGIndex

    db, _tenant_id, ticker = tenant_db
    token = uuid4().hex[:12]

    from app.services.document_ingestion_service import DocumentIngestionService

    result = DocumentIngestionService().ingest_bytes(
        db,
        ticker=ticker,
        title=f"RAG activation note {token}",
        content=_probe_text(token).encode("utf-8"),
        filename="rag-activation.md",
        source_type=SOURCE_TYPE,
        content_type="text/markdown",
    )

    assert result["status"] == "ingested"
    assert result["chunks"] >= 1
    assert result["rag"].get("chunks_indexed", 0) >= 1, result["rag"]
    assert "error" not in result["rag"]

    from qdrant_client.models import FieldCondition, Filter, MatchValue

    count = (
        RAGIndex()
        .client()
        .count(
            collection_name=COLLECTION,
            count_filter=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=result["document_id"]),
                    )
                ]
            ),
        )
    )
    assert count.count >= result["rag"]["chunks_indexed"]


@requires_qdrant
def test_vector_and_unified_search_recover_ingested_chunk(tenant_db):
    from app.services.document_ingestion_service import DocumentIngestionService
    from app.services.rag import RAGIndex
    from app.services.universal_search_service import UniversalSearchService

    db, tenant_id, ticker = tenant_db
    token = uuid4().hex[:12]
    query = f"operating margin discipline evidence {token}"

    result = DocumentIngestionService().ingest_bytes(
        db,
        ticker=ticker,
        title=f"RAG activation search {token}",
        content=_probe_text(token).encode("utf-8"),
        filename="rag-activation-search.md",
        source_type=SOURCE_TYPE,
        content_type="text/markdown",
    )
    doc_id = result["document_id"]

    hits = RAGIndex().search(query, ticker=ticker, limit=5, tenant_id=tenant_id)
    assert any(hit.get("document_id") == doc_id for hit in hits)

    response = UniversalSearchService().search(db, query, ticker=ticker)
    assert response["retrieval"]["vector_status"] == "available"
    assert any(
        row.get("entity_type") == "document_chunk"
        and (row.get("scores", {}).get("vector") or 0) > 0
        for row in response["results"]
    )


def test_vector_ingest_stays_off_without_flag(monkeypatch):
    """Sin el flag, la ingesta no toca Qdrant (ahorra coste/latencia)."""
    monkeypatch.delenv("CAVAAI_ENABLE_VECTOR_INGEST", raising=False)
    db, _tenant_id, ticker = _session_with_tenant()
    try:
        from app.services.document_ingestion_service import DocumentIngestionService

        result = DocumentIngestionService().ingest_bytes(
            db,
            ticker=ticker,
            title="RAG flag-off note",
            content=_probe_text("flagoff").encode("utf-8"),
            filename="rag-flag-off.md",
            source_type=SOURCE_TYPE,
            content_type="text/markdown",
        )
    finally:
        raw_root = Path(f"storage/raw/{ticker}/{SOURCE_TYPE}")
        if raw_root.exists():
            for path in raw_root.glob("*"):
                if path.is_file():
                    path.unlink()
        db.close()
    assert result["status"] == "ingested"
    assert result["rag"].get("chunks_indexed", 0) == 0
    assert "skipped" in result["rag"]
