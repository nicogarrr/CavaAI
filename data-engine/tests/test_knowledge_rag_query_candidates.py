"""La ruta /query pasa la ventana de candidatos configurada a search_knowledge.

Regresion: la ventana estaba fija en 40 (default de search_knowledge) y el
reranker no veia aciertos mas abajo en la fusion (medido: hit@6 21/38 con 40
vs 26/38 con 100 en el dataset piloto). Estos tests fallan si la ruta deja
de pasar el setting o si el default baja de 100.
"""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.routes import knowledge_rag as route_module
from app.core.config import Settings
from app.core.database import Base, get_db
from app.services.knowledge_rag.retrieval import SearchResult


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.info["tenant_id"] = 1
    yield session
    session.close()


def _client(db, monkeypatch, tmp_path: Path, candidates: int) -> tuple[TestClient, dict]:
    settings = Settings(
        _env_file=None,
        knowledge_rag_enabled=True,
        knowledge_rag_inbox_dir=tmp_path,
        knowledge_rag_min_free_gb=0.0,
        knowledge_rag_candidates=candidates,
    )
    monkeypatch.setattr(route_module, "get_settings", lambda: settings)
    monkeypatch.setattr("app.services.knowledge_rag.runtime.get_settings", lambda: settings)
    captured: dict = {}

    def fake_search(query, **kwargs):
        captured.update(kwargs)
        return SearchResult(query=query, citations=[], context="")

    monkeypatch.setattr(route_module, "search_knowledge", fake_search)
    app = FastAPI()
    app.include_router(route_module.router, prefix="/api/knowledge-rag")

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    return TestClient(app), captured


def test_route_passes_configured_candidates(db, monkeypatch, tmp_path) -> None:
    client, captured = _client(db, monkeypatch, tmp_path, candidates=77)
    res = client.post("/api/knowledge-rag/query", json={"query": "margen de seguridad"})
    assert res.status_code == 200
    assert res.json()["abstain"] is True
    assert captured["candidates"] == 77


def test_default_candidates_is_100() -> None:
    assert Settings(_env_file=None).knowledge_rag_candidates == 100
