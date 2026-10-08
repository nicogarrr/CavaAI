"""Consulta: denso + sparse -> RRF -> (reranker) -> padres -> citas verificadas."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from llama_index.core.postprocessor.types import BaseNodePostprocessor
from llama_index.core.schema import NodeRelationship, NodeWithScore, QueryBundle, RelatedNodeInfo, TextNode

from app.services.hybrid_retrieval import RankedId, rrf_fuse
from app.services.knowledge_rag.citations import Citation, format_context, verify_citation
from app.services.knowledge_rag.embedding import Embedder
from app.services.knowledge_rag.store import KnowledgeStore, SearchFilters, build_filter

# parent_id -> (texto del padre, sha256 del padre)
ParentResolver = Callable[[Sequence[str]], dict[str, tuple[str, str]]]


@dataclass
class SearchResult:
    query: str
    citations: list[Citation]
    context: str
    dropped_unverified: int = 0
    candidates: int = 0
    notes: list[str] = field(default_factory=list)


def _overlaps(a: dict[str, Any], b: dict[str, Any]) -> bool:
    if a["parent_id"] != b["parent_id"]:
        return False
    lo = max(a["char_start"], b["char_start"])
    hi = min(a["char_end"], b["char_end"])
    shorter = min(a["char_end"] - a["char_start"], b["char_end"] - b["char_start"]) or 1
    return (hi - lo) / shorter > 0.5


def search_knowledge(
    query: str,
    *,
    tenant_id: int | None,
    store: KnowledgeStore,
    embedder: Embedder,
    resolve_parents: ParentResolver,
    filters: SearchFilters | None = None,
    top_k: int = 6,
    candidates: int = 40,
    postprocessors: Sequence[BaseNodePostprocessor] = (),
    rrf_k: int = 60,
    dense_weight: float = 1.0,
    sparse_weight: float = 1.0,
) -> SearchResult:
    if not query.strip():
        raise ValueError("query is empty")
    flt = build_filter(tenant_id, filters or SearchFilters())
    dense_hits = store.search_dense(embedder.dense([query])[0], flt, candidates)
    sparse_hits = store.search_sparse(embedder.sparse_query(query), flt, candidates)
    payloads = {str(h.id): dict(h.payload or {}) for h in [*dense_hits, *sparse_hits]}
    fused = rrf_fuse(
        [RankedId(str(h.id), float(h.score)) for h in dense_hits],
        [RankedId(str(h.id), float(h.score)) for h in sparse_hits],
        k=rrf_k,
        dense_weight=dense_weight,
        sparse_weight=sparse_weight,
    )
    nodes: list[NodeWithScore] = []
    for hit in fused[:candidates]:
        p = payloads[hit.point_id]
        node = TextNode(
            id_=hit.point_id,
            text=p["text"],
            metadata={**p, "dense_score": hit.dense_score, "sparse_score": hit.sparse_score},
            relationships={NodeRelationship.PARENT: RelatedNodeInfo(node_id=p["parent_id"])},
            excluded_embed_metadata_keys=list(p),
            excluded_llm_metadata_keys=list(p),
        )
        nodes.append(NodeWithScore(node=node, score=hit.fused_score))
    bundle = QueryBundle(query_str=query)
    for post in postprocessors:
        nodes = post.postprocess_nodes(nodes, bundle)

    chosen: list[NodeWithScore] = []
    for n in nodes:
        if any(_overlaps(n.node.metadata, c.node.metadata) for c in chosen):
            continue
        chosen.append(n)
        if len(chosen) >= top_k:
            break

    parents = resolve_parents(sorted({n.node.metadata["parent_id"] for n in chosen}))
    citations: list[Citation] = []
    dropped = 0
    for n in chosen:
        m = n.node.metadata
        parent = parents.get(m["parent_id"])
        if parent is None:
            dropped += 1
            continue
        parent_text, parent_hash = parent
        result = verify_citation(
            quote=n.node.get_content(),
            parent_text=parent_text,
            char_start=m["char_start"],
            char_end=m["char_end"],
            text_sha256=m["text_sha256"],
            parent_text_sha256=parent_hash,
        )
        if not result.ok:
            dropped += 1
            continue
        citations.append(
            Citation(
                number=len(citations) + 1,
                chunk_id=n.node.node_id,
                quote=n.node.get_content(),
                context=parent_text,
                parent_id=m["parent_id"],
                source_id=m["source_id"],
                source_sha256=m["source_sha256"],
                title=m["title"],
                author=m.get("author"),
                source_uri=m["source_uri"],
                language=m["language"],
                doc_type=m["doc_type"],
                corpus=m["corpus"],
                rights=m["rights"],
                published_date=m.get("published_date"),
                as_of=m.get("as_of"),
                section_path=list(m.get("section_path") or []),
                page_start=m.get("page_start"),
                page_end=m.get("page_end"),
                bboxes=list(m.get("bboxes") or []),
                char_start=m["char_start"],
                char_end=m["char_end"],
                text_sha256=m["text_sha256"],
                scores={
                    "rrf": m.get("rrf_score", n.score),
                    "dense": m.get("dense_score"),
                    "sparse": m.get("sparse_score"),
                    "rerank": m.get("rerank_score"),
                },
                verified=True,
                verification=result.checks,
            )
        )
    notes = [] if citations else ["no verified passages: answer must abstain"]
    return SearchResult(
        query=query,
        citations=citations,
        context=format_context(citations),
        dropped_unverified=dropped,
        candidates=len(nodes),
        notes=notes,
    )
