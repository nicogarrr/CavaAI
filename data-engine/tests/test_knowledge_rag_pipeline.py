from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from qdrant_client import QdrantClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.knowledge_rag import KnowledgeRagParent, KnowledgeRagSource
from app.services.knowledge_rag.chunking import ChunkConfig
from app.services.knowledge_rag.citations import verify_citation
from app.services.knowledge_rag.domain import (
    Block,
    DocType,
    ExtractedDocument,
    Section,
    SourceMetadata,
    SourceMetadataError,
    sha256_hex,
)
from app.services.knowledge_rag.ingest import (
    InboxPathError,
    InsufficientDisk,
    check_disk,
    index_source,
    parent_resolver,
    register_source,
    resolve_inbox_path,
)
from app.services.knowledge_rag.rerank import RerankPostprocessor
from app.services.knowledge_rag.retrieval import search_knowledge
from app.services.knowledge_rag.store import KnowledgeStore, SearchFilters
from tests.knowledge_rag_helpers import FakeEmbedder, fake_count

CFG = ChunkConfig(child_max_tokens=50, child_overlap_tokens=8, parent_max_tokens=160)

LETTER_ES = (
    "El margen de seguridad es el principio central de la inversion. "
    "Comprar por debajo del valor intrinseco protege contra el error y la mala suerte. "
    "La volatilidad no es riesgo; el riesgo es la perdida permanente de capital."
)
BOOK_EN = (
    "Mr. Market is a manic depressive business partner who offers prices every day. "
    "The intelligent investor sells to him when he is euphoric and buys when he is despondent."
)
FILING = "Revenue for fiscal 2025 was 4.2 billion dollars and operating margin was 18 percent."


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.info["tenant_id"] = 1
    yield session
    session.close()


@pytest.fixture
def store():
    s = KnowledgeStore(QdrantClient(":memory:"), "knowledge_test")
    s.ensure_collection()
    return s


def _doc(text: str, page: int = 1) -> ExtractedDocument:
    return ExtractedDocument(sections=[Section(("Cap 1",), [Block(text, page=page)])], extractor="fake")


def _ingest(db, store, tmp_path: Path, name: str, text: str, meta: SourceMetadata, tenant: int | None = 1):
    path = tmp_path / name
    path.write_text(text)
    reg = register_source(db, path=path, relative_path=name, meta=meta, tenant_id=tenant)
    if reg.created:
        index_source(
            db,
            reg.source.id,
            path=path,
            store=store,
            embedder=FakeEmbedder(),
            extractor=lambda _p, t=text: _doc(t),
            counter=fake_count,
            config=CFG,
        )
    return reg


def _meta(**kw) -> SourceMetadata:
    base = dict(
        title="Carta Buffett 1990",
        source_uri="https://example.org/carta-1990.pdf",
        language="es",
        doc_type=DocType.LETTER,
        author="Warren Buffett",
        published_date=date(1990, 3, 1),
        rights="public_domain",
    )
    base.update(kw)
    return SourceMetadata(**base)


def _search(db, store, q, **kw):
    return search_knowledge(
        q, tenant_id=1, store=store, embedder=FakeEmbedder(), resolve_parents=parent_resolver(db), **kw
    )


def test_ingest_dedupes_by_checksum_and_is_idempotent(db, store, tmp_path) -> None:
    first = _ingest(db, store, tmp_path, "a.txt", LETTER_ES, _meta())
    again = _ingest(db, store, tmp_path, "copy.txt", LETTER_ES, _meta(title="Otra copia"))
    assert first.created and not again.created and again.source.id == first.source.id
    assert db.scalars(select(KnowledgeRagSource)).all().__len__() == 1
    assert first.source.status == "indexed" and first.source.chunk_count >= 1
    n_points = store.client.count("knowledge_test").count
    index_source(  # ya indexada: no hace nada
        db, first.source.id, path=tmp_path / "a.txt", store=store, embedder=FakeEmbedder(),
        extractor=lambda _p: _doc(LETTER_ES), counter=fake_count, config=CFG,
    )
    assert store.client.count("knowledge_test").count == n_points


def test_query_returns_numbered_verifiable_citations_with_full_provenance(db, store, tmp_path) -> None:
    _ingest(db, store, tmp_path, "a.txt", LETTER_ES, _meta())
    _ingest(db, store, tmp_path, "b.txt", BOOK_EN, _meta(title="Intelligent Investor", author="Benjamin Graham",
            language="en", doc_type=DocType.BOOK, published_date=date(1949, 1, 1)))
    result = _search(db, store, "margen de seguridad valor intrinseco")
    assert result.citations and result.citations[0].title == "Carta Buffett 1990"
    c = result.citations[0]
    assert c.number == 1 and c.verified and c.source_sha256 == sha256_hex(LETTER_ES)
    assert c.author == "Warren Buffett" and c.language == "es" and c.rights == "public_domain"
    assert c.published_date == "1990-03-01" and c.page_start == 1 and c.section_path == ["Cap 1"]
    assert c.context[c.char_start : c.char_end] == c.quote
    assert "[1]" in result.context
    assert sha256_hex(c.quote) == c.text_sha256


def test_filters_author_language_dates_and_corpus_separation(db, store, tmp_path) -> None:
    _ingest(db, store, tmp_path, "a.txt", LETTER_ES, _meta())
    _ingest(db, store, tmp_path, "b.txt", BOOK_EN, _meta(title="Intelligent Investor", author="Benjamin Graham",
            language="en", doc_type=DocType.BOOK, published_date=date(1949, 1, 1)))
    _ingest(db, store, tmp_path, "f.txt", FILING, _meta(title="10-K ACME 2025", author="ACME Inc", language="en",
            doc_type=DocType.FILING, published_date=date(2026, 2, 1), as_of=date(2025, 12, 31)))
    q = "investor revenue margin price"
    assert {c.author for c in _search(db, store, q, top_k=10).citations} <= {"Warren Buffett", "Benjamin Graham"}
    assert _search(db, store, "revenue operating margin").citations == [] or all(
        c.corpus == "evergreen" for c in _search(db, store, "revenue operating margin").citations
    )
    dated = _search(db, store, "revenue operating margin", filters=SearchFilters(corpus="dated"))
    assert [c.corpus for c in dated.citations] == ["dated"] and dated.citations[0].as_of == "2025-12-31"
    only_es = _search(db, store, q, top_k=10, filters=SearchFilters(languages=("es",)))
    assert {c.language for c in only_es.citations} == {"es"}
    graham = _search(db, store, q, top_k=10, filters=SearchFilters(authors=("benjamin graham",)))
    assert {c.author for c in graham.citations} == {"Benjamin Graham"}
    old = _search(db, store, q, top_k=10, filters=SearchFilters(published_to=date(1960, 1, 1)))
    assert {c.title for c in old.citations} == {"Intelligent Investor"}
    later = _search(db, store, "revenue", filters=SearchFilters(corpus="any", as_of_from=date(2026, 1, 1)))
    assert later.citations == []


def test_tenant_isolation(db, store, tmp_path) -> None:
    _ingest(db, store, tmp_path, "a.txt", LETTER_ES, _meta())
    mine = _search(db, store, "margen de seguridad")
    other = search_knowledge(
        "margen de seguridad", tenant_id=2, store=store, embedder=FakeEmbedder(),
        resolve_parents=parent_resolver(db),
    )
    assert mine.citations and other.citations == []


def test_tampered_parent_text_drops_the_citation(db, store, tmp_path) -> None:
    _ingest(db, store, tmp_path, "a.txt", LETTER_ES, _meta())
    parent = db.scalars(select(KnowledgeRagParent)).first()
    parent.text = parent.text.replace("seguridad", "SEGURIDAD")
    db.commit()
    result = _search(db, store, "margen de seguridad")
    assert result.citations == [] and result.dropped_unverified >= 1
    assert "abstain" in result.notes[0]


def test_verify_citation_checks() -> None:
    parent = "uno dos tres cuatro"
    quote = "dos tres"
    good = verify_citation(
        quote=quote, parent_text=parent, char_start=4, char_end=12, text_sha256=sha256_hex(quote),
        parent_text_sha256=sha256_hex(parent), source_bytes=b"orig", source_sha256=sha256_hex(b"orig"),
        reference_page_text="Uno  DOS\ntres cuatro",
    )
    assert good.ok and "source_file_hash" in good.checks and "quote_in_reference_page" in good.checks
    bad = verify_citation(quote="dos cuatro", parent_text=parent, char_start=4, char_end=12,
                          text_sha256=sha256_hex("dos cuatro"), source_bytes=b"x", source_sha256=sha256_hex(b"orig"))
    assert not bad.ok and {"quote_not_in_parent_span", "source_file_hash_mismatch"} <= set(bad.failures)


def test_reranker_hook_reorders_candidates(db, store, tmp_path) -> None:
    _ingest(db, store, tmp_path, "a.txt", LETTER_ES, _meta())
    _ingest(db, store, tmp_path, "b.txt", BOOK_EN, _meta(title="Intelligent Investor", author="Benjamin Graham",
            language="en", doc_type=DocType.BOOK, published_date=date(1949, 1, 1)))

    class PreferGraham:
        def score(self, query: str, passages: list[str]) -> list[float]:
            return [10.0 if "Mr. Market" in p else 0.0 for p in passages]

    q = "margen de seguridad inversion Mr. Market"
    plain = _search(db, store, q, top_k=5)
    ranked = _search(db, store, q, top_k=5, postprocessors=[RerankPostprocessor(reranker=PreferGraham(), top_n=5)])
    assert ranked.citations[0].title == "Intelligent Investor"
    assert ranked.citations[0].scores["rerank"] == 10.0 and ranked.citations[0].scores["rrf"] is not None
    assert plain.citations  # sin hook sigue funcionando


def test_metadata_validation() -> None:
    with pytest.raises(SourceMetadataError):
        _meta(doc_type=DocType.FILING).validate()  # fechado sin as_of
    with pytest.raises(SourceMetadataError):
        _meta(as_of=date(2025, 1, 1)).validate()  # atemporal con as_of
    with pytest.raises(SourceMetadataError):
        _meta(language="fr").validate()
    with pytest.raises(SourceMetadataError):
        _meta(rights="whatever").validate()
    assert _meta(doc_type=DocType.DATASET, as_of=date(2025, 1, 1)).corpus.value == "dated"


def test_inbox_guard_and_disk_guard(tmp_path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "ok.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "secret.pdf").write_bytes(b"%PDF")
    (inbox / "x.exe").write_bytes(b"MZ")
    assert resolve_inbox_path(inbox, "ok.pdf", 1).name == "ok.pdf"
    for bad in ("../secret.pdf", str(tmp_path / "secret.pdf"), "missing.pdf", "x.exe", ""):
        with pytest.raises(InboxPathError):
            resolve_inbox_path(inbox, bad, 1)
    (inbox / "link.pdf").symlink_to(tmp_path / "secret.pdf")
    with pytest.raises(InboxPathError):
        resolve_inbox_path(inbox, "link.pdf", 1)
    check_disk(tmp_path, 0.0)
    with pytest.raises(InsufficientDisk):
        check_disk(tmp_path, 10**9)


def test_failed_extraction_marks_source_failed(db, store, tmp_path) -> None:
    path = tmp_path / "a.txt"
    path.write_text("x")
    reg = register_source(db, path=path, relative_path="a.txt", meta=_meta(), tenant_id=1)

    def boom(_p):
        raise RuntimeError("docling exploded")

    with pytest.raises(RuntimeError):
        index_source(db, reg.source.id, path=path, store=store, embedder=FakeEmbedder(),
                     extractor=boom, counter=fake_count, config=CFG)
    row = db.get(KnowledgeRagSource, reg.source.id)
    assert row.status == "failed" and "docling exploded" in row.error
    # reintento con extractor sano: se recupera sin duplicar
    index_source(db, reg.source.id, path=path, store=store, embedder=FakeEmbedder(),
                 extractor=lambda _p: _doc(LETTER_ES), counter=fake_count, config=CFG)
    assert db.get(KnowledgeRagSource, reg.source.id).status == "indexed"


def test_pilot_scoring_recall_precision_and_abstention() -> None:
    from app.services.knowledge_rag.pilot import PilotCase, score_pilot

    cases = [
        PilotCase("a", "q1", "margen de seguridad", expected_title="T1"),
        PilotCase("b", "q2", "otro fragmento", expected_title="T1"),
        PilotCase("c", "q3", None),
        PilotCase("d", "q4", None),
    ]
    cit = lambda n, title, ctx, ok=True: {  # noqa: E731
        "number": n, "title": title, "context": ctx, "quote": ctx, "source_sha256": "x", "verified": ok}
    responses = {
        "a": [cit(1, "T2", "ruido"), cit(2, "T1", "El  Margen de\nSeguridad es")],
        "b": [cit(1, "T1", "nada")],
        "c": [],
        "d": [cit(1, "T1", "alucinacion")],
    }
    out = score_pilot(cases, responses, ks=(1, 3))
    assert out["recall@1"] == 0.0 and out["recall@3"] == 0.5
    assert out["abstention_rate"] == 0.5
    assert out["citation_verifiable_rate"] == 1.0
    assert out["citation_precision"] == pytest.approx(1 / 3)
