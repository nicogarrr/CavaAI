"""Ronda 5 auditor #990: la ruta general NO emite datos de mercado.

Decidido por main bajo preferencias de Nico (cero terminal / secretos
fuera de chat): cualquier cifra con divisa o porcentaje en contexto
financiero cae a la abstencion honesta; los datos cuantitativos viven
solo en la ruta estructurada con ticker. La charla ordinaria queda
natural.
"""

import asyncio

from app.schemas import ChatResponse
from app.services.chat_service import ChatService
from app.services.chat_synthesis_service import ChatSynthesisService
from tests.test_chat_general_es import StubProvider, _db

SRC = [
    {
        "type": "market_price",
        "id": "mp1",
        "title": "ASTS (cierre 2026-10-09, test)",
        "price": "1999.00 USD",
    }
]


def _grounded(text, sources):
    return ChatSynthesisService._general_text_grounded(
        text, ChatResponse(answer="", sources=sources)
    )


def test_no_market_figures_even_with_perfect_source_and_citation():
    # ruta general: ni con fuente perfecta y cita valida
    assert not _grounded("ASTS cotiza a 1999 USD [market_price:mp1]", SRC)
    assert not _grounded("ASTS cotiza a $999", [])
    assert not _grounded("ASTS cotiza a 999 dólares", [])
    assert not _grounded("ASTS cotiza a 999 usd", [])
    assert not _grounded("rentabilidad 35%", [])


def test_auditor_round5_repros():
    assert not _grounded("msft cotiza a 1999USD [market_price:mp1]", SRC)
    assert not _grounded("Microsoft cotiza a 1999USD [market_price:mp1]", SRC)
    assert not _grounded("ASTS vale 1999 millones USD [market_price:mp1]", SRC)
    assert not _grounded("ASTS cotiza a 1999GBP [market_price:mp1]", SRC)


def test_fabricated_citation_still_rejected():
    assert not _grounded("El cielo es azul [market_price:999999].", SRC)


def test_english_still_rejected():
    assert not _grounded(
        "Hello! The price to earnings ratio is the price divided by earnings.", []
    )


def test_ordinary_chat_stays_natural():
    assert _grounded("Son las 5 y tengo 3 hermanos", [])
    assert _grounded("La batería está al 35%", [])
    assert _grounded("El PER es el precio dividido por beneficio.", [])
    assert _grounded("¡Hola! ¿Qué tal tu día?", [])


def test_financial_intent_without_company_abstains_without_llm():
    db = _db()
    provider = StubProvider()
    result = asyncio.run(
        ChatService(provider).answer(
            db, "¿a cuánto cotiza FooCorp?", "portfolio", None
        )
    )
    assert provider.requests == []
    assert result.model == "abstain"
    assert "ticker" in result.answer


def test_llm_market_figure_falls_back_honestly():
    provider = StubProvider("ASTS cotiza a 1999 USD [market_price:mp1]")
    result = asyncio.run(
        ChatSynthesisService(provider).synthesize_general(
            question="precio", baseline=ChatResponse(answer="sin datos", sources=SRC)
        )
    )
    assert "1999" not in result.answer
    assert result.llm_trace.get("fallback") is True
