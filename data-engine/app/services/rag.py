from qdrant_client import QdrantClient

from app.core.config import get_settings


class RAGIndex:
    collection_name = "portfolio_research_documents"
    vector_size = 384

    def __init__(self) -> None:
        self.settings = get_settings()

    def client(self) -> QdrantClient:
        return QdrantClient(url=self.settings.qdrant_url)

    def _embedder(self):
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer("all-MiniLM-L6-v2")

    def _ensure_collection(self, client: QdrantClient) -> None:
        from qdrant_client.models import Distance, VectorParams
        collections = [c.name for c in client.get_collections().collections]
        if self.collection_name not in collections:
            client.create_collection(
                self.collection_name,
                vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
            )

    def ingest_document(self, db, document) -> dict:
        from sqlalchemy.orm import Session
        from app.models import DocumentChunk
        from sqlalchemy import select
        from qdrant_client.models import PointStruct
        import uuid

        tenant_id = db.info.get("tenant_id")
        if tenant_id is None or document.tenant_id != tenant_id:
            raise ValueError("Tenant context is required to index a document")

        chunks = list(db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document.id)
            .order_by(DocumentChunk.chunk_index)
        ).all())

        if not chunks:
            return {"chunks_indexed": 0, "collection": self.collection_name}

        texts = [c.text for c in chunks]
        embedder = self._embedder()
        vectors = embedder.encode(texts, normalize_embeddings=True).tolist()

        ticker = None
        if document.company_id:
            from app.models import Company
            company = db.get(Company, document.company_id)
            ticker = company.ticker if company else None

        points = []
        for chunk, vector in zip(chunks, vectors):
            if chunk.qdrant_point_id:
                point_id = chunk.qdrant_point_id
            else:
                point_id = str(uuid.uuid4())
                chunk.qdrant_point_id = point_id
            points.append(PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "text": chunk.text,
                    "ticker": ticker,
                    "document_id": document.id,
                    "chunk_index": chunk.chunk_index,
                    "entity_type": "document_chunk",
                    "entity_id": chunk.id,
                    "source_type": document.source_type,
                    "title": document.title,
                    "tenant_id": tenant_id,
                },
            ))

        try:
            client = self.client()
            self._ensure_collection(client)
            client.upsert(collection_name=self.collection_name, points=points)
            db.commit()
        except Exception as exc:
            return {"chunks_indexed": 0, "error": str(exc), "collection": self.collection_name}

        return {"chunks_indexed": len(points), "collection": self.collection_name}

    def ingest_knowledge_document(self, db, document) -> dict:
        import uuid

        from qdrant_client.models import PointStruct
        from sqlalchemy import select

        from app.models import KnowledgeChunk

        tenant_id = db.info.get("tenant_id")
        if tenant_id is None or document.tenant_id != tenant_id:
            raise ValueError("Tenant context is required to index knowledge")
        chunks = list(
            db.scalars(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.knowledge_document_id == document.id)
                .order_by(KnowledgeChunk.chunk_index)
            ).all()
        )
        if not chunks:
            return {"chunks_indexed": 0, "collection": self.collection_name}
        vectors = self._embedder().encode(
            [chunk.content for chunk in chunks], normalize_embeddings=True
        ).tolist()
        points = []
        for chunk, vector in zip(chunks, vectors):
            point_id = chunk.qdrant_point_id or str(uuid.uuid4())
            chunk.qdrant_point_id = point_id
            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "text": chunk.content,
                        "title": document.title,
                        "source_type": document.document_type,
                        "knowledge_document_id": document.id,
                        "collection_id": document.collection_id,
                        "chunk_index": chunk.chunk_index,
                        "page_number": chunk.page_number,
                        "entity_type": "knowledge_chunk",
                        "entity_id": chunk.id,
                        "tenant_id": tenant_id,
                    },
                )
            )
        try:
            client = self.client()
            self._ensure_collection(client)
            client.upsert(collection_name=self.collection_name, points=points)
            db.commit()
        except Exception as exc:
            return {
                "chunks_indexed": 0,
                "error": str(exc),
                "collection": self.collection_name,
            }
        return {"chunks_indexed": len(points), "collection": self.collection_name}

    def rebuild_tenant(self, db) -> dict:
        """Recreate one tenant's disposable Qdrant index from PostgreSQL chunks."""
        from qdrant_client.models import (
            FieldCondition,
            Filter,
            FilterSelector,
            MatchValue,
        )
        from sqlalchemy import select
        from app.models import Document, KnowledgeDocument

        tenant_id = db.info.get("tenant_id")
        if tenant_id is None:
            raise ValueError("Tenant context is required to rebuild the vector index")

        client = self.client()
        self._ensure_collection(client)
        client.delete(
            collection_name=self.collection_name,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(
                            key="tenant_id",
                            match=MatchValue(value=tenant_id),
                        )
                    ]
                )
            ),
            wait=True,
        )

        documents = list(
            db.scalars(
                select(Document)
                .where(Document.tenant_id == tenant_id)
                .order_by(Document.id)
            ).all()
        )
        indexed = 0
        errors: list[dict] = []
        for document in documents:
            result = self.ingest_document(db, document)
            indexed += int(result.get("chunks_indexed", 0))
            if result.get("error"):
                errors.append({"document_id": document.id, "error": result["error"]})
        knowledge_documents = list(
            db.scalars(select(KnowledgeDocument).order_by(KnowledgeDocument.id)).all()
        )
        for document in knowledge_documents:
            result = self.ingest_knowledge_document(db, document)
            indexed += int(result.get("chunks_indexed", 0))
            if result.get("error"):
                errors.append(
                    {"knowledge_document_id": document.id, "error": result["error"]}
                )
        return {
            "tenant_id": tenant_id,
            "documents": len(documents),
            "knowledge_documents": len(knowledge_documents),
            "chunks_indexed": indexed,
            "errors": errors,
            "collection": self.collection_name,
        }

    def search(
        self,
        query: str,
        ticker: str | None = None,
        limit: int = 5,
        tenant_id: int | None = None,
    ) -> list[dict]:
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        if tenant_id is None:
            return []
        try:
            embedder = self._embedder()
            vector = embedder.encode([query], normalize_embeddings=True)[0].tolist()
            client = self.client()
            self._ensure_collection(client)
            conditions = []
            if ticker:
                conditions.append(
                    FieldCondition(
                        key="ticker", match=MatchValue(value=ticker)
                    )
                )
            conditions.append(
                FieldCondition(
                    key="tenant_id",
                    match=MatchValue(value=tenant_id),
                )
            )
            query_filter = Filter(must=conditions) if conditions else None
            results = client.search(
                collection_name=self.collection_name,
                query_vector=vector,
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
            )
            return [
                {
                    "text": r.payload.get("text", ""),
                    "ticker": r.payload.get("ticker"),
                    "document_id": r.payload.get("document_id"),
                    "source_type": r.payload.get("source_type"),
                    "title": r.payload.get("title"),
                    "score": r.score,
                    "point_id": r.id,
                    "entity_type": r.payload.get("entity_type"),
                    "entity_id": r.payload.get("entity_id"),
                    "chunk_index": r.payload.get("chunk_index"),
                }
                for r in results
            ]
        except Exception:
            return []

    def status(self) -> dict:
        try:
            collections = self.client().get_collections()
            return {"configured": True, "collections": [c.name for c in collections.collections]}
        except Exception as exc:
            return {"configured": False, "error": str(exc)}
