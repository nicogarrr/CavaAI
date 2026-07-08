"""Knowledge-base facade.

Qdrant is the only supported vector backend. ChromaDB data files and fallback
code were intentionally removed to avoid cross-ticker leakage and hidden local
state.
"""

from __future__ import annotations

from typing import Optional

from modules.vector_store import QdrantVectorStore

KnowledgeBase = QdrantVectorStore

_kb_instance: Optional[QdrantVectorStore] = None


def get_knowledge_base() -> QdrantVectorStore:
    global _kb_instance
    if _kb_instance is None:
        _kb_instance = QdrantVectorStore()
    return _kb_instance


def reset_knowledge_base() -> None:
    global _kb_instance
    _kb_instance = None
