"""El denso del conocimiento es PROPIO (v2c del piloto): no toca el vector chat legacy.

Regresion cubierta: hasta este cambio el knowledge RAG reusaba
rag_dense_model/rag_dense_dims (MiniLM 384, los del portfolio_research legacy).
Subir a e5-large por esa via habria reindexado el chat legacy en 1024 dims
contra una coleccion creada a 384.
"""

from __future__ import annotations

from datetime import date

from qdrant_client import QdrantClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import Base
from app.services.knowledge_rag import runtime
from app.services.knowledge_rag.chunking import ChunkConfig
from app.services.knowledge_rag.domain import Block, DocType, ExtractedDocument, Section, SourceMetadata
from app.services.knowledge_rag.ingest import register_source
from app.services.knowledge_rag.jobs import run_ingest_job
from app.services.knowledge_rag.store import KnowledgeStore
from tests.knowledge_rag_helpers import FakeEmbedder, fake_count

CFG = ChunkConfig(child_max_tokens=50, child_overlap_tokens=8, parent_max_tokens=160)


def _meta() -> SourceMetadata:
    return SourceMetadata(
        "Carta", "https://e.org/c.pdf", "es", DocType.LETTER, "public_domain", "A", date(1990, 1, 1)
    )


def _doc(text: str) -> ExtractedDocument:
    return ExtractedDocument([Section(("C",), [Block(text, page=1)])], "fake")


def test_dense_defaults_son_v2c_y_el_legacy_no_cambia() -> None:
    s = Settings(_env_file=None)
    assert s.knowledge_rag_dense_model == "intfloat/multilingual-e5-large"
    assert s.knowledge_rag_dense_dims == 1024
    # El legacy (vector chat de portfolio_research_documents) sigue en MiniLM 384.
    assert s.rag_dense_model == "sentence-transformers/all-MiniLM-L6-v2"
    assert s.rag_dense_dims == 384


def test_dense_override_por_entorno(monkeypatch) -> None:
    monkeypatch.setenv("KNOWLEDGE_RAG_DENSE_MODEL", "org/modelo-x")
    monkeypatch.setenv("KNOWLEDGE_RAG_DENSE_DIMS", "768")
    s = Settings(_env_file=None)
    assert s.knowledge_rag_dense_model == "org/modelo-x"
    assert s.knowledge_rag_dense_dims == 768


def test_make_embedder_usa_el_modelo_del_conocimiento(monkeypatch) -> None:
    seen: dict[str, str] = {}

    class Spy:
        def __init__(self, dense: str, sparse: str, dims: int = 0) -> None:
            seen["dense"] = dense
            seen["sparse"] = sparse

    monkeypatch.setattr(runtime, "LocalEmbedder", Spy)
    runtime.make_embedder(
        Settings(_env_file=None, rag_dense_model="legacy", knowledge_rag_dense_model="conocimiento")
    )
    assert seen["dense"] == "conocimiento"


def test_make_store_usa_las_dims_del_conocimiento(monkeypatch) -> None:
    seen: dict[str, int] = {}

    class SpyStore:
        def __init__(self, client, collection: str, dims: int) -> None:
            seen["dims"] = dims

    monkeypatch.setattr(runtime, "KnowledgeStore", SpyStore)
    import qdrant_client

    monkeypatch.setattr(qdrant_client, "QdrantClient", lambda *a, **k: object())
    runtime.make_store(
        Settings(
            _env_file=None, qdrant_url="http://qdrant:6333", rag_dense_dims=384, knowledge_rag_dense_dims=1024
        )
    )
    assert seen["dims"] == 1024


def test_el_job_cuenta_tokens_con_el_modelo_del_conocimiento(tmp_path, monkeypatch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'd.sqlite'}")
    Base.metadata.create_all(engine)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    text = "El margen de seguridad protege contra el error. La volatilidad no es riesgo."
    (inbox / "c.txt").write_text(text)
    settings = Settings(
        _env_file=None,
        knowledge_rag_enabled=True,
        knowledge_rag_inbox_dir=inbox,
        knowledge_rag_min_free_gb=0.0,
    )
    store = KnowledgeStore(QdrantClient(":memory:"), "kd")
    with Session(engine) as db:
        db.info["tenant_id"] = 1
        sid = register_source(
            db, path=inbox / "c.txt", relative_path="c.txt", meta=_meta(), tenant_id=1
        ).source.id
        called: list[str] = []
        monkeypatch.setattr(runtime, "make_counter", lambda model: called.append(model) or fake_count)
        out = run_ingest_job(
            db,
            sid,
            settings,
            store=store,
            embedder=FakeEmbedder(),
            extractor=lambda _p: _doc(text),
            config=CFG,
        )
        assert out["status"] == "ok"
        assert called == [settings.knowledge_rag_dense_model]
