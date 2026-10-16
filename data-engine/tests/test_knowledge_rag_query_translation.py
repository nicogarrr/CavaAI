"""F372: traduccion de consulta ES->EN en el RAG de conocimiento.

Regresion cubierta: una pregunta en espanol no alcanzaba doctrina indexada en
ingles (BM25 no cruza idiomas; medido en el piloto v2c, docs/knowledge-rag.md).
La busqueda con la variante traducida tiene que encontrarla, y sin LLM
disponible todo sigue funcionando solo con la consulta original.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.routes import knowledge_rag as route_module
from app.core.config import Settings
from app.core.database import Base, get_db
from app.llm.adapters import OpenAICompatibleProvider
from app.llm.model_aliases import MODEL_ALIASES, OPENCODE_GO_MODEL_ALIASES, ModelAlias
from app.services.knowledge_rag import query_translation
from app.services.knowledge_rag.chunking import ChunkConfig
from app.services.knowledge_rag.domain import Block, DocType, ExtractedDocument, Section, SourceMetadata
from app.services.knowledge_rag.ingest import index_source, parent_resolver, register_source
from app.services.knowledge_rag.retrieval import SearchResult, search_knowledge
from app.services.knowledge_rag.store import KnowledgeStore
from tests.knowledge_rag_helpers import FakeEmbedder, fake_count

CFG = ChunkConfig(child_max_tokens=50, child_overlap_tokens=8, parent_max_tokens=160)

LETTER_ES = (
    "El margen de seguridad es el principio central de la inversion. "
    "Comprar por debajo del valor intrinseco protege contra el error y la mala suerte."
)
BOOK_EN = (
    "Mr. Market is a manic depressive business partner who offers prices every day. "
    "The intelligent investor sells to him when he is euphoric and buys when he is despondent."
)


@pytest.fixture(autouse=True)
def clear_translation_cache():
    query_translation._cache.clear()
    yield
    query_translation._cache.clear()


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
    s = KnowledgeStore(QdrantClient(":memory:"), "knowledge_qt_test")
    s.ensure_collection()
    return s


def _ingest(db, store, tmp_path: Path, name: str, text: str, meta: SourceMetadata):
    path = tmp_path / name
    path.write_text(text)
    reg = register_source(db, path=path, relative_path=name, meta=meta, tenant_id=1)
    if reg.created:
        index_source(
            db,
            reg.source.id,
            path=path,
            store=store,
            embedder=FakeEmbedder(),
            extractor=lambda _p: ExtractedDocument(
                sections=[Section(("Cap 1",), [Block(text, page=1)])], extractor="fake"
            ),
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


class _Provider:
    def __init__(self, text: str = "", *, exc: Exception | None = None, degraded: bool = False):
        self.text = text
        self.exc = exc
        self.degraded = degraded
        self.calls = 0

    async def complete(self, request):
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        return SimpleNamespace(text=self.text, degraded=self.degraded)


# --- heuristica de idioma ---


def test_looks_spanish_detects_spanish_questions() -> None:
    assert query_translation.looks_spanish("¿Qué dice Buffett sobre el margen de seguridad?")
    assert query_translation.looks_spanish("que dice graham sobre las empresas")  # sin tildes
    assert query_translation.looks_spanish("carta de inversión")


def test_looks_spanish_ignores_english_questions() -> None:
    assert not query_translation.looks_spanish("What does Buffett say about moats?")
    assert not query_translation.looks_spanish("Apple buyback yield 2025")


# --- limpieza de la salida del LLM ---


def test_clean_translation_strips_quotes_and_whitespace() -> None:
    assert query_translation._clean_translation('  "What  does Buffett say?"\n') == "What does Buffett say?"


def test_clean_translation_rejects_garbage() -> None:
    assert query_translation._clean_translation("") is None
    assert query_translation._clean_translation("12345 !!!") is None
    assert query_translation._clean_translation("x" * 500) is None


# --- english_variant (doble del proveedor, sin red) ---


@pytest.mark.anyio
async def test_english_variant_skips_non_spanish_without_llm() -> None:
    provider = _Provider(exc=AssertionError("no debe llamarse"))
    variant, note = await query_translation.english_variant("What does Graham say about Mr Market?", provider=provider)
    assert (variant, note) == (None, None)
    assert provider.calls == 0


@pytest.mark.anyio
async def test_english_variant_refuses_unverified_model_without_calling() -> None:
    settings = Settings(_env_file=None, opencode_go_model="paid-model-x")
    provider = _Provider(exc=AssertionError("no debe llamarse"))
    variant, note = await query_translation.english_variant(
        "¿Qué dice Buffett sobre las empresas?", settings=settings, provider=provider
    )
    assert variant is None and note is not None
    assert provider.calls == 0


@pytest.mark.anyio
async def test_english_variant_translates_and_caches() -> None:
    provider = _Provider("What does Buffett say about the margin of safety?")
    variant, note = await query_translation.english_variant(
        "¿Qué dice Buffett sobre el margen de seguridad?", provider=provider
    )
    assert variant == "What does Buffett say about the margin of safety?" and note is None
    again, note = await query_translation.english_variant(
        "¿Qué dice Buffett sobre el margen de seguridad?", provider=provider
    )
    assert again == variant and note is None
    assert provider.calls == 1  # la segunda sale de la cache


@pytest.mark.anyio
async def test_english_variant_fails_closed_on_provider_error() -> None:
    provider = _Provider(exc=RuntimeError("caido"))
    variant, note = await query_translation.english_variant(
        "¿Qué dice Buffett sobre las empresas?", provider=provider
    )
    assert variant is None and note is not None and "RuntimeError" in note
    # El fallo queda cacheado unos minutos: no martillea al proveedor caido.
    variant, note = await query_translation.english_variant(
        "¿Qué dice Buffett sobre las empresas?", provider=provider
    )
    assert variant is None and note is not None
    assert provider.calls == 1


@pytest.mark.anyio
async def test_english_variant_fails_closed_on_degraded_or_invalid() -> None:
    degraded, note = await query_translation.english_variant(
        "¿Qué dice Buffett sobre las empresas?", provider=_Provider("ok", degraded=True)
    )
    assert degraded is None and note is not None
    invalid, note = await query_translation.english_variant(
        "¿Qué dicen los inversores sobre las carteras?", provider=_Provider("")
    )
    assert invalid is None and note is not None


@pytest.mark.anyio
async def test_english_variant_ignores_translation_equal_to_query() -> None:
    variant, note = await query_translation.english_variant(
        "¿inversión?", provider=_Provider("¿inversión?")
    )
    assert (variant, note) == (None, None)



# --- guard de coste sobre el ID resuelto, factory real y complete interceptado ---


@pytest.fixture
def restore_alias_registry():
    yield
    MODEL_ALIASES.replace(OPENCODE_GO_MODEL_ALIASES)


def _remap_alias(alias: str, provider_model_id: str) -> None:
    """Simula un alias persistido en DB apuntando a otro ID de proveedor."""
    MODEL_ALIASES.replace(
        ModelAlias(
            internal_alias=a.internal_alias,
            provider=a.provider,
            provider_model_id=provider_model_id if a.internal_alias == alias else a.provider_model_id,
            enabled=a.enabled,
            context_window=a.context_window,
            input_cost=a.input_cost,
            output_cost=a.output_cost,
            supported_capabilities=a.supported_capabilities,
            cost_basis=a.cost_basis,
        )
        for a in OPENCODE_GO_MODEL_ALIASES
    )


@pytest.mark.anyio
async def test_alias_remapped_to_paid_id_is_refused_before_complete(monkeypatch, restore_alias_registry) -> None:
    """Canario: un alias "gratuito" cuyo ID resuelto es de pago NO se llama."""
    _remap_alias("deepseek-v4.1-flash-free", "paid-model-canary")
    settings = Settings(
        _env_file=None, opencode_go_model="deepseek-v4.1-flash-free", opencode_go_api_key="sk-test"
    )

    async def forbidden_complete(self, request):
        raise AssertionError("complete no debe llamarse con un ID resuelto de pago")

    monkeypatch.setattr(OpenAICompatibleProvider, "complete", forbidden_complete)
    variant, note = await query_translation.english_variant(
        "¿Qué dice Buffett sobre las empresas?", settings=settings
    )
    assert variant is None and note is not None


@pytest.mark.anyio
async def test_cascade_provider_is_refused_without_network(monkeypatch, restore_alias_registry) -> None:
    """La cascada (Gemini/OpenRouter pueden cobrar) no es un proveedor valido."""
    settings = Settings(_env_file=None, llm_provider="cascade", opencode_go_api_key="sk-test")

    async def forbidden_complete(self, request):
        raise AssertionError("complete no debe llamarse con la cascada")

    monkeypatch.setattr(OpenAICompatibleProvider, "complete", forbidden_complete)
    variant, note = await query_translation.english_variant(
        "¿Qué dice Buffett sobre las empresas?", settings=settings
    )
    assert variant is None and note is not None


@pytest.mark.anyio
async def test_factory_error_degrades_to_original_query(monkeypatch, restore_alias_registry) -> None:
    """Un ValueError del factory degrada a la consulta original, nunca lanza."""
    def broken_factory(settings, *, client=None):
        raise ValueError("configuracion LLM invalida")

    monkeypatch.setattr(query_translation, "create_llm_provider", broken_factory)
    settings = Settings(_env_file=None, opencode_go_api_key="sk-test")
    variant, note = await query_translation.english_variant(
        "¿Qué dice Buffett sobre las empresas?", settings=settings
    )
    assert variant is None and note is not None and "ValueError" in note


@pytest.mark.anyio
async def test_real_factory_with_intercepted_complete(monkeypatch, restore_alias_registry) -> None:
    """Cableado real (factory + router de aliases) con la red interceptada."""
    settings = Settings(
        _env_file=None, opencode_go_model="deepseek-v4.1-flash-free", opencode_go_api_key="sk-test"
    )
    seen: dict = {}

    async def fake_complete(self, request):
        seen["resolved_model"] = self.model_router.resolve(request)
        return SimpleNamespace(text="What does Buffett say about companies?", degraded=False)

    monkeypatch.setattr(OpenAICompatibleProvider, "complete", fake_complete)
    variant, note = await query_translation.english_variant(
        "¿Qué dice Buffett sobre las empresas?", settings=settings
    )
    assert variant == "What does Buffett say about companies?" and note is None
    assert seen["resolved_model"] == "deepseek-v4.1-flash-free"

# --- fusion de variantes en retrieval (Qdrant en memoria, embedder falso) ---


def test_variant_reaches_english_doctrine(db, store, tmp_path) -> None:
    _ingest(db, store, tmp_path, "carta.txt", LETTER_ES, _meta())
    _ingest(
        db,
        store,
        tmp_path,
        "libro.txt",
        BOOK_EN,
        _meta(
            title="The Intelligent Investor",
            source_uri="https://example.org/tii.epub",
            language="en",
            doc_type=DocType.BOOK,
            author="Benjamin Graham",
            published_date=date(1949, 1, 1),
        ),
    )
    result = search_knowledge(
        "que dice graham sobre el mercado maniaco",
        tenant_id=1,
        store=store,
        embedder=FakeEmbedder(),
        resolve_parents=parent_resolver(db),
        query_variants=["mr market manic depressive business partner"],
    )
    assert result.query_variants == ["mr market manic depressive business partner"]
    assert result.citations[0].title == "The Intelligent Investor"


def test_variant_equal_to_query_is_deduped(db, store, tmp_path) -> None:
    _ingest(db, store, tmp_path, "carta.txt", LETTER_ES, _meta())
    result = search_knowledge(
        "margen de seguridad",
        tenant_id=1,
        store=store,
        embedder=FakeEmbedder(),
        resolve_parents=parent_resolver(db),
        query_variants=["MARGEN  DE   SEGURIDAD", ""],
    )
    assert result.query_variants == []


# --- ruta /query ---


def _client(db, monkeypatch, tmp_path: Path, *, translation: bool = True):
    settings = Settings(
        _env_file=None,
        knowledge_rag_enabled=True,
        knowledge_rag_inbox_dir=tmp_path,
        knowledge_rag_min_free_gb=0.0,
        knowledge_rag_query_translation=translation,
    )
    monkeypatch.setattr(route_module, "get_settings", lambda: settings)
    monkeypatch.setattr("app.services.knowledge_rag.runtime.get_settings", lambda: settings)
    captured: dict = {}

    def fake_search(query, **kwargs):
        captured.update(kwargs)
        return SearchResult(query=query, citations=[], context="", query_variants=list(kwargs.get("query_variants") or []))

    monkeypatch.setattr(route_module, "search_knowledge", fake_search)
    app = FastAPI()
    app.include_router(route_module.router, prefix="/api/knowledge-rag")

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    return TestClient(app), captured


def test_route_searches_with_translation_variant(db, monkeypatch, tmp_path) -> None:
    async def fake_variant(query, *, settings=None, provider=None):
        return "margin of safety principle", None

    monkeypatch.setattr(query_translation, "english_variant", fake_variant)
    client, captured = _client(db, monkeypatch, tmp_path)
    res = client.post("/api/knowledge-rag/query", json={"query": "margen de seguridad"})
    assert res.status_code == 200
    assert captured["query_variants"] == ["margin of safety principle"]
    assert res.json()["query_variants"] == ["margin of safety principle"]
    assert res.json()["notes"] == []


def test_route_surfaces_translation_degradation_note(db, monkeypatch, tmp_path) -> None:
    async def fake_variant(query, *, settings=None, provider=None):
        return None, "traduccion de consulta no disponible (ProviderDisabledError)"

    monkeypatch.setattr(query_translation, "english_variant", fake_variant)
    client, captured = _client(db, monkeypatch, tmp_path)
    res = client.post("/api/knowledge-rag/query", json={"query": "margen de seguridad"})
    assert res.status_code == 200
    assert captured["query_variants"] == []
    assert res.json()["query_variants"] == []
    assert res.json()["notes"] == ["traduccion de consulta no disponible (ProviderDisabledError)"]


def test_route_skips_translation_when_flag_off(db, monkeypatch, tmp_path) -> None:
    async def forbidden(query, *, settings=None, provider=None):
        raise AssertionError("no debe llamarse con el flag apagado")

    monkeypatch.setattr(query_translation, "english_variant", forbidden)
    client, captured = _client(db, monkeypatch, tmp_path, translation=False)
    res = client.post("/api/knowledge-rag/query", json={"query": "margen de seguridad"})
    assert res.status_code == 200
    assert captured["query_variants"] == []


def test_translation_flag_defaults_on() -> None:
    assert Settings(_env_file=None).knowledge_rag_query_translation is True
