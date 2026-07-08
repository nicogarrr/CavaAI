"""Qdrant vector-store facade for RAG."""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Protocol

from sentence_transformers import SentenceTransformer


class VectorStore(Protocol):
    def add_document(self, content: str, metadata: Optional[Dict] = None, document_id: Optional[str] = None) -> Dict:
        ...

    def search(
        self,
        query: str,
        n_results: int = 10,
        collection_names: Optional[List[str]] = None,
        symbol: Optional[str] = None,
        general_only: bool = False,
    ) -> List[Dict]:
        ...

    def delete_document(self, document_id: str) -> bool:
        ...

    def list_documents(self, limit: int = 100) -> List[Dict]:
        ...

    def stats(self) -> Dict:
        ...


class QdrantVectorStore:
    """Qdrant implementation for new RAG deployments."""

    def __init__(self, url: Optional[str] = None, collection_name: str = "knowledge"):
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        self.collection_name = collection_name
        self.client = QdrantClient(url=url or os.getenv("QDRANT_URL", "http://localhost:6333"))
        self.embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE),
            )

    def _chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
        if len(text) <= chunk_size:
            return [text]
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunks.append(text[start:end].strip())
            start = end - overlap
        return [chunk for chunk in chunks if chunk]

    def _generate_id(self, content: str) -> str:
        return hashlib.md5(content.encode()).hexdigest()[:16]

    def add_document(self, content: str, metadata: Optional[Dict] = None, document_id: Optional[str] = None) -> Dict:
        from qdrant_client.models import PointStruct

        chunks = self._chunk_text(content)
        embeddings = self.embedding_model.encode(chunks).tolist()
        base_id = document_id or self._generate_id(content)
        base_metadata = metadata.copy() if metadata else {}
        base_metadata["document_id"] = base_id
        base_metadata["added_at"] = datetime.now().isoformat()
        base_metadata["total_chunks"] = len(chunks)

        points = []
        for i, chunk in enumerate(chunks):
            payload = base_metadata.copy()
            payload["chunk_index"] = i
            payload["chunk_preview"] = chunk[:100] + "..." if len(chunk) > 100 else chunk
            payload["content"] = chunk
            point_id = str(uuid.UUID(hex=hashlib.md5(f"{base_id}:{i}".encode()).hexdigest()))
            points.append(PointStruct(id=point_id, vector=embeddings[i], payload=payload))

        self.client.upsert(collection_name=self.collection_name, points=points)
        return {"success": True, "document_id": base_id, "chunks_added": len(chunks), "collection": self.collection_name}

    def search(
        self,
        query: str,
        n_results: int = 10,
        collection_names: Optional[List[str]] = None,
        symbol: Optional[str] = None,
        general_only: bool = False,
    ) -> List[Dict]:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        _ = collection_names
        query_vector = self.embedding_model.encode([query])[0].tolist()
        query_filter = None
        if symbol:
            query_filter = Filter(must=[FieldCondition(key="symbol", match=MatchValue(value=symbol.upper()))])
        hits = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            query_filter=query_filter,
            limit=n_results if symbol else max(n_results, n_results * 4),
        )
        results = [
            {
                "content": hit.payload.get("content", "") if hit.payload else "",
                "score": hit.score,
                "metadata": {k: v for k, v in (hit.payload or {}).items() if k != "content"},
            }
            for hit in hits
        ]
        if general_only:
            results = [result for result in results if not result["metadata"].get("symbol")]
        return results[:n_results]

    def delete_document(self, document_id: str) -> bool:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        self.client.delete(
            collection_name=self.collection_name,
            points_selector=Filter(must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]),
        )
        return True

    def list_documents(self, limit: int = 100) -> List[Dict]:
        points, _ = self.client.scroll(collection_name=self.collection_name, limit=limit, with_payload=True)
        docs = {}
        for point in points:
            payload = point.payload or {}
            doc_id = payload.get("document_id", str(point.id))
            docs.setdefault(doc_id, {
                "id": doc_id,
                "title": payload.get("title", "Sin título"),
                "added_at": payload.get("added_at", ""),
                "chunks": payload.get("total_chunks", 1),
                "preview": payload.get("chunk_preview", ""),
            })
        return list(docs.values())[:limit]

    def stats(self) -> Dict:
        info = self.client.get_collection(self.collection_name)
        return {"total_chunks": info.points_count, "collection": self.collection_name, "backend": "qdrant"}

    def get_stats(self) -> Dict:
        return self.stats()

    def get_context_for_analysis(self, symbol: str, company_name: str) -> str:
        queries = [
            (f"{symbol} {company_name}", symbol, False),
            (f"análisis {company_name} value investing", symbol, False),
            ("criterios inversión valoración ROIC margen", None, True),
        ]
        all_context = []
        seen_content = set()
        for query, query_symbol, general_only in queries:
            for result in self.search(query=query, n_results=5, symbol=query_symbol, general_only=general_only):
                content_key = result["content"][:100]
                if content_key not in seen_content:
                    seen_content.add(content_key)
                    all_context.append(result["content"])
        if all_context:
            return "## 📚 Mi Base de Conocimiento Personal:\n\n" + "\n\n---\n\n".join(all_context[:8])
        return ""
