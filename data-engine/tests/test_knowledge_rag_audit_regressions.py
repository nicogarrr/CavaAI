"""Regresiones de la auditoria de #924: ids por tenant, pool, limites y estado failed."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import QueuePool

from app.api.routes import knowledge_rag as route_module
from app.core.config import Settings
from app.core.database import Base, get_db
from app.models.knowledge_rag import KnowledgeRagParent, KnowledgeRagSource
from app.services.knowledge_rag import runtime
from app.services.knowledge_rag.chunking import ChunkConfig, ChunkingError, chunk_document
from app.services.knowledge_rag.domain import Block, DocType, ExtractedDocument, Section, SourceMetadata
from app.services.knowledge_rag.ingest import index_source, parent_resolver, register_source
from app.services.knowledge_rag.jobs import run_ingest_job
from app.services.knowledge_rag.retrieval import search_knowledge
from app.services.knowledge_rag.store import KnowledgeStore
from app.services.knowledge_rag.tokens import heuristic_counter
from tests.knowledge_rag_helpers import FakeEmbedder, fake_count

TEXT = "El margen de seguridad protege contra el error. La volatilidad no es riesgo."
CFG = ChunkConfig(child_max_tokens=50, child_overlap_tokens=8, parent_max_tokens=160)


def _meta() -> SourceMetadata:
    return SourceMetadata("Carta", "https://e.org/c.pdf", "es", DocType.LETTER, "public_domain", "A", date(1990, 1, 1))


def _doc(text: str = TEXT) -> ExtractedDocument:
    return ExtractedDocument([Section(("C",), [Block(text, page=1)])], "fake")


def test_same_bytes_in_two_tenants_keep_separate_ids_and_both_searchable(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    Base.metadata.create_all(engine)
    store = KnowledgeStore(QdrantClient(":memory:"), "kt")
    store.ensure_collection()
    path = tmp_path / "a.txt"
    path.write_text(TEXT)
    for tenant in (1, 2):
        with Session(engine) as db:
            db.info["tenant_id"] = tenant
            reg = register_source(db, path=path, relative_path="a.txt", meta=_meta(), tenant_id=tenant)
            assert reg.created
            index_source(db, reg.source.id, path=path, store=store, embedder=FakeEmbedder(),
                         extractor=lambda _p: _doc(), counter=fake_count, config=CFG)
    with Session(engine) as db:
        parents = db.scalars(select(KnowledgeRagParent)).all()
        assert len({p.id for p in parents}) == len(parents) == 2
    assert store.client.count("kt").count == 2
    for tenant in (1, 2):
        with Session(engine) as db:
            db.info["tenant_id"] = tenant
            res = search_knowledge("margen de seguridad", tenant_id=tenant, store=store,
                                   embedder=FakeEmbedder(), resolve_parents=parent_resolver(db))
            assert len(res.citations) == 1 and res.citations[0].verified


def test_no_db_connection_held_during_extraction_embedding_and_qdrant(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'p.sqlite'}", poolclass=QueuePool, pool_size=1, max_overflow=0)
    Base.metadata.create_all(engine)
    seen: list[str] = []

    def probe(label: str) -> None:
        seen.append(label)
        assert engine.pool.checkedout() == 0, f"connection held during {label}"  # type: ignore[attr-defined]

    class ProbeStore(KnowledgeStore):
        def ensure_collection(self):
            probe("ensure_collection")
            super().ensure_collection()

        def delete_source(self, *a, **k):
            probe("delete_source")
            super().delete_source(*a, **k)

        def upsert(self, *a, **k):
            probe("upsert")
            super().upsert(*a, **k)

    class ProbeEmbedder(FakeEmbedder):
        def dense(self, texts):
            probe("dense")
            return super().dense(texts)

    store = ProbeStore(QdrantClient(":memory:"), "kp")
    path = tmp_path / "a.txt"
    path.write_text(TEXT)
    with Session(engine, expire_on_commit=True) as db:
        db.info["tenant_id"] = 1
        reg = register_source(db, path=path, relative_path="a.txt", meta=_meta(), tenant_id=1)
        index_source(db, reg.source.id, path=path, store=store, embedder=ProbeEmbedder(),
                     extractor=lambda _p: (probe("extract"), _doc())[1], counter=fake_count, config=CFG)
        assert {"extract", "ensure_collection", "delete_source", "dense", "upsert"} <= set(seen)
        assert db.get(KnowledgeRagSource, reg.source.id).status == "indexed"


def test_query_releases_the_connection_before_embedding_and_qdrant(tmp_path, monkeypatch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'q.sqlite'}", poolclass=QueuePool, pool_size=1, max_overflow=0,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    store = KnowledgeStore(QdrantClient(":memory:"), "kq")
    store.ensure_collection()
    held: list[int] = []

    class ProbeEmbedder(FakeEmbedder):
        def dense(self, texts):
            held.append(engine.pool.checkedout())  # type: ignore[attr-defined]
            return super().dense(texts)

    settings = Settings(_env_file=None, knowledge_rag_enabled=True)
    monkeypatch.setattr(route_module, "get_settings", lambda: settings)
    monkeypatch.setattr(runtime, "get_settings", lambda: settings)
    monkeypatch.setattr(runtime, "make_store", lambda _s: store)
    monkeypatch.setattr(runtime, "make_embedder", lambda _s: ProbeEmbedder())
    app = FastAPI()
    app.include_router(route_module.router, prefix="/api/knowledge-rag")

    def _db():
        db = Session(engine)
        db.info["tenant_id"] = 1
        db.scalar(select(KnowledgeRagSource.id).limit(1))  # lookup de tenant de get_db: deja txn abierta
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db
    res = TestClient(app).post("/api/knowledge-rag/query", json={"query": "margen de seguridad"})
    assert res.status_code == 200 and held == [0]


def test_unsplittable_block_is_hard_split_and_limits_hold() -> None:
    block = "." * 1000  # sin espacios: el contador oficial da >1.300 tokens
    cfg = ChunkConfig()
    assert heuristic_counter(block) > 1000
    parents, children = chunk_document(_doc(block), title="T", source_sha256="ab" * 32,
                                       count=heuristic_counter, config=cfg)
    assert children and max(c.token_count for c in children) <= cfg.child_max_tokens
    assert all(heuristic_counter(p.text) <= cfg.parent_max_tokens for p in parents)
    by_id = {p.id: p for p in parents}
    assert all(by_id[c.parent_id].text[c.char_start : c.char_end] == c.text for c in children)


def test_oversized_chunk_fails_loudly_instead_of_truncating() -> None:
    with pytest.raises(ChunkingError):
        chunk_document(_doc("palabra " * 50), title="T", source_sha256="ab" * 32,
                       count=lambda t: 400, config=ChunkConfig())  # contador que nunca cabe
    with pytest.raises(ValueError):
        ChunkConfig(child_max_tokens=200, parent_max_tokens=300)


def _job_env(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'j.sqlite'}")
    Base.metadata.create_all(engine)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    settings = Settings(_env_file=None, knowledge_rag_enabled=True, knowledge_rag_inbox_dir=inbox,
                        knowledge_rag_min_free_gb=0.0)
    return engine, inbox, settings


def test_permanent_job_failure_persists_failed_and_explicit_retry_works(tmp_path, monkeypatch) -> None:
    engine, inbox, settings = _job_env(tmp_path)
    (inbox / "c.txt").write_text(TEXT)
    store = KnowledgeStore(QdrantClient(":memory:"), "kj")
    with Session(engine) as db:
        db.info["tenant_id"] = 1
        reg = register_source(db, path=inbox / "c.txt", relative_path="c.txt", meta=_meta(), tenant_id=1)
        sid = reg.source.id
        (inbox / "c.txt").unlink()  # el fichero desaparece antes del actor
        out = run_ingest_job(db, sid, settings, store=store)
        assert out["status"] == "error" and "InboxPathError" in out["error"]
        row = db.get(KnowledgeRagSource, sid)
        assert row.status == "failed" and "InboxPathError" in (row.error or "")
    # reponer + POST de los mismos bytes: dedupe de una fuente failed => re-encola
    (inbox / "c.txt").write_text(TEXT)
    sent: list[int] = []
    import app.workers.knowledge_rag_actors as actors

    monkeypatch.setattr(actors.ingest_knowledge_source, "send", lambda s, **_k: sent.append(s))
    monkeypatch.setattr(route_module, "get_settings", lambda: settings)
    monkeypatch.setattr(runtime, "get_settings", lambda: settings)
    app = FastAPI()
    app.include_router(route_module.router, prefix="/api/knowledge-rag")

    def _db():
        with Session(engine) as d:
            d.info["tenant_id"] = 1
            yield d

    app.dependency_overrides[get_db] = _db
    body = {"path": "c.txt", "title": "Carta", "source_uri": "https://e.org/c.pdf", "language": "es",
            "doc_type": "letter", "rights": "public_domain"}
    res = TestClient(app).post("/api/knowledge-rag/sources", json=body)
    assert res.status_code == 200 and res.json()["requeued"] is True and sent == [sid]
    assert res.json()["status"] == "queued" and res.json()["error"] is None
    with Session(engine) as db:
        db.info["tenant_id"] = 1
        out = run_ingest_job(db, sid, settings, store=store, embedder=FakeEmbedder(),
                             extractor=lambda _p: _doc(), counter=fake_count, config=CFG)
        assert out["status"] == "ok" and db.get(KnowledgeRagSource, sid).status == "indexed"
    # queued/indexed no se re-encolan
    again = TestClient(app).post("/api/knowledge-rag/sources", json=body)
    assert again.json()["requeued"] is False and sent == [sid]


def test_disabled_flag_and_transient_errors_mark_failed(tmp_path) -> None:
    engine, inbox, settings = _job_env(tmp_path)
    (inbox / "c.txt").write_text(TEXT)
    off = Settings(_env_file=None, knowledge_rag_enabled=False, knowledge_rag_inbox_dir=inbox)
    with Session(engine) as db:
        db.info["tenant_id"] = 1
        sid = register_source(db, path=inbox / "c.txt", relative_path="c.txt", meta=_meta(), tenant_id=1).source.id
        assert run_ingest_job(db, sid, off)["status"] == "error"
        assert db.get(KnowledgeRagSource, sid).status == "failed"

        class Boom(FakeEmbedder):
            def dense(self, texts):
                raise ConnectionError("qdrant down")

        with pytest.raises(ConnectionError):
            run_ingest_job(db, sid, settings, store=KnowledgeStore(QdrantClient(":memory:"), "kb"),
                           embedder=Boom(), extractor=lambda _p: _doc(), counter=fake_count, config=CFG)
        row = db.get(KnowledgeRagSource, sid)
        assert row.status == "failed" and "qdrant down" in row.error
