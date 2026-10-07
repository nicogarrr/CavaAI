"""Actor Dramatiq de ingesta del RAG de conocimiento.

Modulo propio (como thesis_backtest_actors) para no tocar dramatiq_app.py mas
de una linea. Registrado con ``import app.workers.knowledge_rag_actors`` en
dramatiq_app.py: sin ese import el actor se despacha pero nadie lo consume.

Cola dedicada ``knowledge``: Docling es pesado en RAM/CPU y no debe competir con
las colas default/kpis/theses. El worker que la consuma debe arrancarse con
``dramatiq app.workers.dramatiq_app --queues knowledge`` (ver docs/knowledge-rag.md).
"""

from __future__ import annotations

from typing import Any

import dramatiq

from app.workers.dramatiq_app import _handle_actor_error, _session
from app.workers.dramatiq_app import broker as _broker  # noqa: F401

KNOWLEDGE_QUEUE_NAME = "knowledge"


@dramatiq.actor(max_retries=1, min_backoff=60_000, queue_name=KNOWLEDGE_QUEUE_NAME, time_limit=3_600_000)
def ingest_knowledge_source(
    source_id: int,
    *,
    tenant_id: int | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Indexa una fuente ya registrada (checksum ya deduplicado por la API)."""
    from app.core.config import get_settings
    from app.models.knowledge_rag import KnowledgeRagSource
    from app.services.knowledge_rag import runtime
    from app.services.knowledge_rag.ingest import (
        InboxPathError,
        InsufficientDisk,
        check_disk,
        index_source,
        resolve_inbox_path,
    )

    settings = get_settings()
    db = _session(tenant_id, user_id)
    try:
        runtime.require_enabled(settings)
        source = db.get(KnowledgeRagSource, source_id)
        if source is None:
            return {"actor": "ingest_knowledge_source", "status": "error", "error": "source not found"}
        check_disk(settings.knowledge_rag_inbox_dir, settings.knowledge_rag_min_free_gb)
        path = resolve_inbox_path(
            settings.knowledge_rag_inbox_dir, source.filename, settings.knowledge_rag_max_file_mb
        )
        return index_source(
            db,
            source_id,
            path=path,
            store=runtime.make_store(settings),
            embedder=runtime.make_embedder(settings),
            extractor=runtime.make_extractor(settings),
            counter=runtime.make_counter(settings.rag_dense_model),
            config=runtime.chunk_config(settings),
        )
    except (runtime.KnowledgeRagDisabled, InsufficientDisk, InboxPathError, ValueError) as exc:
        # Permanentes: reintentar no cambia nada (disco, flag, ruta, contenido).
        return {"actor": "ingest_knowledge_source", "status": "error", "error": f"{type(exc).__name__}: {exc}"}
    except Exception as exc:
        return _handle_actor_error("ingest_knowledge_source", exc, source_id=source_id)
    finally:
        db.close()
