"""Embeddings locales: denso MiniLM (ONNX/fastembed) + sparse BM25.

Reutiliza app.services.hybrid_retrieval (misma cache de modelos). La diferencia
con el RAG de portfolio: el BM25 de documentos y de consulta se calculan por
separado (``embed`` vs ``query_embed``), porque la coleccion usa modifier IDF.
"""

from __future__ import annotations

from typing import Any, Protocol

from app.services.hybrid_retrieval import (
    DEFAULT_DENSE_MODEL,
    DEFAULT_SPARSE_MODEL,
    SparseEmbedding,
    _cached_model,
    embed_dense,
)


class Embedder(Protocol):
    dims: int

    def dense(self, texts: list[str]) -> list[list[float]]: ...

    def sparse_docs(self, texts: list[str]) -> list[SparseEmbedding]: ...

    def sparse_query(self, text: str) -> SparseEmbedding: ...


class LocalEmbedder:
    dims = 384

    def __init__(self, dense_model: str = DEFAULT_DENSE_MODEL, sparse_model: str = DEFAULT_SPARSE_MODEL):
        self.dense_model = dense_model
        self.sparse_model = sparse_model

    def dense(self, texts: list[str]) -> list[list[float]]:
        return embed_dense(texts, self.dense_model)

    def _sparse(self) -> Any:
        from fastembed import SparseTextEmbedding

        return _cached_model("sparse", SparseTextEmbedding, self.sparse_model)

    def sparse_docs(self, texts: list[str]) -> list[SparseEmbedding]:
        return [
            SparseEmbedding(indices=list(v.indices), values=list(v.values))
            for v in self._sparse().embed(texts)
        ]

    def sparse_query(self, text: str) -> SparseEmbedding:
        vec = next(iter(self._sparse().query_embed(text)))
        return SparseEmbedding(indices=list(vec.indices), values=list(vec.values))
