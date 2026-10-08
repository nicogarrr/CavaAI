"""Hook de reranker CPU pequeno (opcional) como postprocesador de LlamaIndex."""

from __future__ import annotations

from typing import Any, Protocol

from llama_index.core.postprocessor.types import BaseNodePostprocessor
from llama_index.core.schema import NodeWithScore, QueryBundle
from pydantic import ConfigDict


class Reranker(Protocol):
    def score(self, query: str, passages: list[str]) -> list[float]: ...


class FastembedReranker:
    """Cross-encoder ONNX via fastembed. ``Xenova/ms-marco-MiniLM-L-6-v2`` (~80 MB,
    Apache-2.0) es SOLO ingles; para espanol hace falta un multilingue
    (p. ej. ``BAAI/bge-reranker-v2-m3-int8``, ~570 MB: ver docs/knowledge-rag.md).
    """

    def __init__(self, model: str = "Xenova/ms-marco-MiniLM-L-6-v2") -> None:
        self.model = model
        self._encoder: Any = None

    def score(self, query: str, passages: list[str]) -> list[float]:
        if self._encoder is None:
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            self._encoder = TextCrossEncoder(self.model)
        return [float(s) for s in self._encoder.rerank(query, passages)]


class RerankPostprocessor(BaseNodePostprocessor):
    """Reordena nodos por el score del reranker; conserva el score RRF en metadata."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    reranker: Any
    top_n: int = 10

    @classmethod
    def class_name(cls) -> str:
        return "KnowledgeRerankPostprocessor"

    def _postprocess_nodes(
        self, nodes: list[NodeWithScore], query_bundle: QueryBundle | None = None
    ) -> list[NodeWithScore]:
        if not nodes or query_bundle is None:
            return nodes
        scores = self.reranker.score(query_bundle.query_str, [n.node.get_content() for n in nodes])
        out: list[NodeWithScore] = []
        for node, score in zip(nodes, scores, strict=True):
            node.node.metadata["rrf_score"] = node.score
            node.node.metadata["rerank_score"] = float(score)
            out.append(NodeWithScore(node=node.node, score=float(score)))
        out.sort(key=lambda n: (-(n.score or 0.0), n.node.node_id))
        return out[: self.top_n]
