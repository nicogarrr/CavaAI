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


def test_auditor_round6_repros():
    # Candado semantico: la AFIRMACION de mercado/cartera se bloquea en
    # cualquier formato, no solo cuando la cifra es detectable.
    assert not _grounded("ASTS cotiza a 999", [])  # sin moneda
    assert not _grounded("ASTS cotiza a novecientos dólares", [])  # deletreada
    assert not _grounded(
        "Tu rentabilidad es del treinta y cinco por ciento", []
    )  # cartera sin cifra numerica
    assert not _grounded("ASTS cotiza a $-999", [])  # signo
    assert not _grounded("ASTS cotiza a 999CAD", [])  # divisa no listada
    assert not _grounded("Microsoft cotiza a novecientos dólares", [])  # sin ticker
    assert not _grounded("AAPL ha subido mucho esta semana", [])  # sin cifra
    assert not _grounded("Mi cartera va muy bien este año", [])  # posicion propia


def test_round6_conceptual_stays_natural():
    assert _grounded("El PER es el precio dividido por beneficio.", [])
    assert _grounded("La cotización bursátil refleja expectativas.", [])
    assert _grounded("Un ETF replica un índice.", [])


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
            question="Cuéntame algo", baseline=ChatResponse(answer="sin datos", sources=SRC)
        )
    )
    assert "1999" not in result.answer
    assert result.llm_trace.get("fallback") is True


# ---- Ronda 7: ruta LIMITADA (decision de producto: veracidad primero) ----
from app.services.chat_synthesis_service import _general_scope  # noqa: E402


def _general(question, llm_text):
    provider = StubProvider(llm_text)
    result = asyncio.run(
        ChatSynthesisService(provider).synthesize_general(
            question=question,
            baseline=ChatResponse(answer="", sources=SRC),
        )
    )
    return provider, result


def test_round7_scope_classification():
    assert _general_scope("Hola, cuéntame un chiste") == "ordinary"
    assert _general_scope("¿Qué hora es en Tokio?") == "ordinary"
    assert _general_scope("¿Qué es el PER?") == "concept"
    assert _general_scope("¿Cómo funciona un ETF?") == "concept"
    assert _general_scope("¿Cómo va mi cartera?") == "abstain"
    assert _general_scope("¿Qué es el PER de ASTS?") == "abstain"
    assert _general_scope("cuánto vale Microsoft") == "abstain"


def test_round7_financial_specific_never_reaches_llm():
    for q in ["¿Cómo va mi cartera?", "¿Cuánto han subido mis acciones?", "precio de ASTS"]:
        provider, result = _general(q, "cualquier cosa")
        assert provider.requests == []
        assert result.model == "abstain"
        assert result.sources == []


def test_round7_llm_never_gets_private_context():
    provider, _ = _general("Cuéntame un chiste", "Ahí va un chiste sobre gatos.")
    payload = provider.requests[0].messages[1].content
    assert "retrieved_sources" not in payload
    assert "mp1" not in payload and "1999" not in payload


def test_round7_auditor_round6_outputs_rejected():
    # El generador alucina afirmaciones financieras: rechazadas en ambos alcances.
    bad = [
        "Microsoft cotiza a novecientos",
        "asts cotiza a 999",
        "El precio de Microsoft es novecientos",
        "Tus acciones han duplicado su valor",
        "La cartera tiene una ganancia de treinta por ciento",
    ]
    for text in bad:
        _, r1 = _general("Cuéntame algo", text)  # ordinaria
        assert r1.llm_trace.get("fallback") is True, text
        _, r2 = _general("¿Qué es el PER?", text)  # concepto
        assert r2.llm_trace.get("fallback") is True, text


def test_round7_conversation_and_concepts_stay_natural():
    _, r = _general("Cuéntame un chiste", "Ahí va: ¿qué le dice un gato a otro? Miau.")
    assert r.model == "stub" and not r.llm_trace.get("fallback")
    _, r = _general(
        "¿Qué es el PER?",
        "El PER relaciona lo que pagas por una empresa con lo que gana cada año.",
    )
    assert not r.llm_trace.get("fallback")
    assert r.sources == []
