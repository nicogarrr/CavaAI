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
                    "source_type": document.source_type,
                    "title": document.title,
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

    def search(self, query: str, ticker: str | None = None, limit: int = 5) -> list[dict]:
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        try:
            embedder = self._embedder()
            vector = embedder.encode([query], normalize_embeddings=True)[0].tolist()
            client = self.client()
            self._ensure_collection(client)
            query_filter = None
            if ticker:
                query_filter = Filter(must=[FieldCondition(key="ticker", match=MatchValue(value=ticker))])
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
