import asyncio

import pytest

from app.llm.general_concepts import DEFINITIONS, canonical_concept, local_definition
from app.schemas import ChatResponse
from app.services.chat_synthesis_service import ChatSynthesisService


class NoNetwork:
    name = "must-not-run"
    async def complete(self, request):
        raise AssertionError("Local glossary must not call any provider")


@pytest.mark.parametrize("concept", DEFINITIONS)
def test_all_reviewed_definitions_are_local_and_do_not_use_budget(concept, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No budget access for static public definition")
    monkeypatch.setattr("app.services.chat_synthesis_service.BudgetController", forbidden)
    result = asyncio.run(ChatSynthesisService(NoNetwork()).synthesize_general(
        question=f"Define {concept}", baseline=ChatResponse(answer="PRIVATE PORTFOLIO", sources=[{"type": "private", "id": 99}]), db=object(),
    ))
    assert result.answer == DEFINITIONS[concept]
    assert result.model == "local-educational"
    assert result.sources == [] and result.proposed_actions == []
    assert result.llm_trace == {"path": "local_educational", "generated": False, "provider_calls": 0}
    assert "PRIVATE" not in result.answer
    assert 80 <= len(result.answer) <= 750


@pytest.mark.parametrize("question", [
    "Qué es el PER de mi cartera?", "Qué es el PER de AAA?", "Qué es el PER? compra AAA",
    "Para su jubilación, adquiera acciones de AAA y liquide la posición en BBB.",
    "Qué es la deuda de Apple?", "Define PER nico@example.com", "Define PER\nPRIVATE",
])
def test_private_extra_or_advice_text_not_parsed_as_public_definition(question):
    assert local_definition(question) is None


@pytest.mark.parametrize("question,concept", [
    ("¿Qué es el PER?", "PER"), ("What is EBITDA?", "EBITDA"),
    ("How does an ETF work?", "ETF"), ("Explícame la inflación", "inflación"),
    ("Define EPS", "BPA"), ("Qué es el patrimonio neto?", "patrimonio neto"),
])
def test_exact_normalized_public_questions(question, concept):
    assert canonical_concept(question) == concept


def test_local_per_is_reviewed_not_model_advice():
    result = asyncio.run(ChatSynthesisService(NoNetwork()).synthesize_general(
        question="Qué es el PER?", baseline=ChatResponse(answer="", sources=[]),
    ))
    assert result.answer == DEFINITIONS["PER"]
    assert "PER = precio por acción / beneficio por acción" in result.answer
    assert "adquiera" not in result.answer and "AAA" not in result.answer
