"""Logica del trabajo de ingesta (separada del actor para poder probarla sin broker)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.knowledge_rag import KnowledgeRagSource
from app.services.knowledge_rag import runtime
from app.services.knowledge_rag.chunking import ChunkingError
from app.services.knowledge_rag.ingest import (
    InboxPathError,
    InsufficientDisk,
    check_disk,
    index_source,
    mark_failed,
    resolve_inbox_path,
)

# Errores permanentes: reintentar no cambia nada (flag, disco, ruta, contenido).
PERMANENT = (
    runtime.KnowledgeRagDisabled,
    InsufficientDisk,
    InboxPathError,
    ChunkingError,
    ValueError,
)


def run_ingest_job(db: Session, source_id: int, settings: Settings, **deps: Any) -> dict[str, Any]:
    """Ejecuta la ingesta. Todo fallo deja la fuente en ``failed`` con su motivo.

    Permanente -> devuelve ``status: error`` (sin reintento de dramatiq).
    Otro error -> ``failed`` + se relanza para que dramatiq reintente; el
    reintento vuelve a poner ``processing``.
    """
    if db.get(KnowledgeRagSource, source_id) is None:
        db.rollback()
        return {"actor": "ingest_knowledge_source", "status": "error", "error": "source not found"}
    db.rollback()
    try:
        runtime.require_enabled(settings)
        check_disk(settings.knowledge_rag_inbox_dir, settings.knowledge_rag_min_free_gb)
        source = db.get(KnowledgeRagSource, source_id)
        filename = source.filename if source is not None else ""
        db.rollback()
        path = resolve_inbox_path(settings.knowledge_rag_inbox_dir, filename, settings.knowledge_rag_max_file_mb)
        return index_source(
            db,
            source_id,
            path=path,
            store=deps.get("store") or runtime.make_store(settings),
            embedder=deps.get("embedder") or runtime.make_embedder(settings),
            extractor=deps.get("extractor") or runtime.make_extractor(settings),
            counter=deps.get("counter") or runtime.make_counter(settings.rag_dense_model),
            config=deps.get("config") or runtime.chunk_config(settings),
        )
    except PERMANENT as exc:
        message = f"{type(exc).__name__}: {exc}"
        mark_failed(db, source_id, message)
        return {"actor": "ingest_knowledge_source", "status": "error", "error": message}
    except Exception as exc:
        mark_failed(db, source_id, f"{type(exc).__name__}: {exc}")
        raise
