"""Cerebro único: marca GerarAI, contexto de página resuelto en servidor y
cerebro de solo lectura."""

import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, Company, MemoryItem
from app.schemas import ChatPageContext
from app.services.brain_service import (
    BRAND_NAME,
    resolve_page_context,
    small_talk_answer,
)
from app.services.chat_service import ChatService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        session.add(
            Company(
                ticker="ASTS", name="AST SpaceMobile", exchange="NASDAQ", currency="USD",
                sector="Tech", industry="Satellites", company_type="holding",
                valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
            )
        )
        session.commit()
        yield session


class _LLMCaido:
    name = "caido"

    async def complete(self, request):
        raise RuntimeError("proveedor caido")


def test_marca_es_gerarai_en_el_saludo():
    answer = small_talk_answer("hola")
    assert BRAND_NAME == "GerarAI"
    assert "GerarAI" in answer
    assert "CavaAI" not in answer


def test_contexto_de_pagina_none_sin_pagina(db):
    assert resolve_page_context(db, None) is None


def test_contexto_de_pagina_resuelve_ticker_en_servidor(db):
    page = ChatPageContext(path="/research/ASTS", label="ASTS", ticker="asts")
    resolved = resolve_page_context(db, page)
    assert resolved is not None
    assert resolved.company is not None and resolved.company.ticker == "ASTS"
    echo = resolved.echo()
    assert echo["ticker"] == "ASTS"
    assert echo["company_name"] == "AST SpaceMobile"
    assert echo["company_resolved"] is True
    assert echo["label"] == "ASTS"


def test_contexto_de_pagina_con_ticker_desconocido_no_inventa_empresa(db):
    page = ChatPageContext(path="/research/NOPE", label=None, ticker="NOPE")
    resolved = resolve_page_context(db, page)
    assert resolved is not None
    assert resolved.company is None
    echo = resolved.echo()
    assert echo["company_resolved"] is False
    assert echo["company_name"] is None
    # La pastilla conserva una etiqueta honesta (el propio ticker pedido).
    assert echo["label"] == "NOPE"


def test_answer_usa_el_ticker_de_la_pagina_y_devuelve_el_eco(db):
    page = ChatPageContext(path="/research/ASTS", label="ASTS", ticker="ASTS")
    response = asyncio.run(
        ChatService(_LLMCaido()).answer(db, "que evidencia hay?", "portfolio", None, use_jev=False, page=page)
    )
    assert response.context is not None
    assert response.context["ticker"] == "ASTS"
    assert response.context["company_resolved"] is True
    # La empresa de la página guía la respuesta estructurada.
    assert "ASTS" in response.answer
    # Solo lectura: la pregunta no escribió memoria.
    assert db.query(MemoryItem).count() == 0


def test_la_mencion_explicita_gana_al_ticker_de_la_pagina(db):
    db.add(
        Company(
            ticker="MSFT", name="Microsoft", exchange="NASDAQ", currency="USD",
            sector="Tech", industry="Software", company_type="holding",
            valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
        )
    )
    db.commit()
    page = ChatPageContext(path="/research/ASTS", label="ASTS", ticker="ASTS")
    response = asyncio.run(
        ChatService(_LLMCaido()).answer(db, "tesis de MSFT?", "portfolio", None, use_jev=False, page=page)
    )
    assert "MSFT" in response.answer


def test_library_page_context_keeps_model_until_resolved(db, monkeypatch):
    from app.api.routes import knowledge
    from app.services import knowledge_chat
    async def fake_ask(*args, **kwargs):
        assert 'page' not in kwargs
        return {'answer': 'Respuesta sintética', 'sources': []}
    monkeypatch.setattr(knowledge_chat, 'ask_library', fake_ask)
    payload=knowledge.LibraryQuestion(question='Pregunta sintética', page=ChatPageContext(path='/research/ASTS',ticker='ASTS'))
    # No worker thread touches this SQLite session: fake bridge executes locally.
    async def immediate(thunk): return thunk()
    monkeypatch.setattr(knowledge, 'run_in_threadpool', immediate)
    result=asyncio.run(knowledge.chat_library(payload,db))
    assert result['context']['ticker']=='ASTS'
    assert result['context']['company_resolved'] is True
