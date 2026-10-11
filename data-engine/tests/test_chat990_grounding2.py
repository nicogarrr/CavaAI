"""Ronda 2 auditor #990: vinculo cifra-divisa-compania-cita y abstencion.

Decidido por main bajo preferencias de Nico (cero terminal / secretos
fuera de chat): las cifras financieras salen de las fuentes, nunca del
modelo; sin compania resuelta, la intencion financiera se abstiene.
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


def test_money_without_sources_is_rejected():
    assert not _grounded("ASTS cotiza a $999", [])
    assert not _grounded("ASTS cotiza a 999 dólares", [])
    assert not _grounded("ASTS cotiza a 999 usd", [])
    assert not _grounded("rentabilidad 35%", [])


def test_substring_figure_and_currency_mismatch_rejected():
    # "999" es substring de "1999" en la fuente: no vale
    assert not _grounded("ASTS cotiza a 999 USD [market_price:mp1]", SRC)
    # divisa distinta a la de la fuente: no vale
    assert not _grounded("ASTS cotiza a 1999 EUR [market_price:mp1]", SRC)
    assert not _grounded("Otro activo 999 EUR [market_price:mp1]", SRC)


def test_exact_figure_currency_and_citation_accepted():
    assert _grounded("ASTS cotiza a 1999 USD [market_price:mp1]", SRC)
    assert _grounded("ASTS cotiza a 1999.00 USD [market_price:mp1]", SRC)


def test_ordinary_chat_numbers_are_not_blocked():
    assert _grounded("Son las 5 y tengo 3 hermanos", [])
    assert _grounded("La batería está al 35%", [])


def test_financial_percent_requires_source_backing():
    assert not _grounded("rentabilidad 35% [market_price:mp1]", SRC)


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


def test_concept_question_still_goes_to_general_route():
    db = _db()
    provider = StubProvider("El PER es el precio dividido por beneficio.")
    result = asyncio.run(
        ChatService(provider).answer(db, "que es el PER", "portfolio", None, use_jev=False)
    )
    assert result.model != "abstain"
    assert "PER" in result.answer


def test_decimal_point_is_never_dropped():
    # 19.99 USD no valida contra una fuente de 1999 USD (100x de error)
    assert not _grounded("ASTS cotiza a 19.99 USD [market_price:mp1]", SRC)
    assert not _grounded("rentabilidad 3.5% [market_price:mp1]", SRC)
    # miles con separador si equivalen
    src_miles = [
        {
            "type": "market_price",
            "id": "mp2",
            "title": "ASTS (cierre 2026-10-09, test)",
            "price": "1,999.00 USD",
        }
    ]
    assert _grounded("ASTS cotiza a 1999 USD [market_price:mp2]", src_miles)


def test_cross_company_figure_is_rejected():
    # la fuente es de ASTS: no valida la misma cifra atribuida a MSFT
    assert not _grounded("MSFT cotiza a 1999 USD [market_price:mp1]", SRC)


def test_financial_claim_without_citation_is_rejected():
    assert not _grounded("ASTS cotiza a 1999 USD.", SRC)
    assert _grounded("ASTS cotiza a 1999 USD [market_price:mp1]", SRC)
