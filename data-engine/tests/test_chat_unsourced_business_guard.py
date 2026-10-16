"""Owner rule: knowledge/inference is allowed without pretending it is official."""
import asyncio

import pytest

from app.schemas import ChatResponse
from app.services.chat_synthesis_service import ChatSynthesisService, _general_scope
from app.services.prompt_registry import get_prompt
from tests.test_chat_general_es import StubProvider


@pytest.mark.parametrize('question', [
    'ingresos de apple', 'Explícame los ingresos de apple',
    'EXPLÍCAME LOS INGRESOS DE APPLE', 'Qué es la deuda de nvidia',
    'qué es la deuda de NvIdIa', 'how large is the workforce at nvidia',
    'How large is the workforce at NVIDIA', 'define revenue of apple',
    'what is EBITDA of nvidia?', 'ingresos de Apple 2031',
])
def test_company_knowledge_can_reach_model_with_explicit_inference(question):
    answer = '[INFERIDO] Sin fuentes verificadas, podría depender de sus productos y servicios. No puedo confirmar el estado actual.'
    p = StubProvider(answer)
    result = asyncio.run(ChatSynthesisService(p).synthesize_general(
        question=question, baseline=ChatResponse(answer='', sources=[]),
    ))
    assert _general_scope(question) == 'inferred'
    assert p.requests
    assert result.answer == answer
    assert result.sources == []
    assert 'reviewed_at_utc' in p.requests[0].messages[1].content


@pytest.mark.parametrize('answer', [
    'apple obtiene ingresos de sus productos.',
    '[OFICIAL] nvidia mantiene deuda corporativa.',
    '[INFERIDO] nvidia tiene 999999 empleados.',
    '[INFERIDO] Sin fuentes, podría tener deuda.\n\nnvidia mantiene deuda corporativa.',
    '[INFERIDO] nvidia mantiene deuda corporativa.',
    '[INFERIDO] Sin fuentes, podría ser así [financial_fact:999].',
])
def test_missing_or_false_evidence_labels_never_publish(answer):
    p = StubProvider(answer)
    result = asyncio.run(ChatSynthesisService(p).synthesize_general(
        question='deuda de nvidia', baseline=ChatResponse(answer='', sources=[]),
    ))
    assert result.model == 'fallback'
    assert result.answer != answer


@pytest.mark.parametrize('answer', [
    '[SIN_DATOS] No tengo una base razonable para cuantificar la plantilla actual.',
    '[INFERIDO] Sin fuentes verificadas, podría haber un rango estimado de 10 a 20 como ejemplo hipotético, no dato de la empresa.',
])
def test_honest_no_data_or_qualified_estimate_is_allowed(answer):
    p = StubProvider(answer)
    result = asyncio.run(ChatSynthesisService(p).synthesize_general(
        question='empleados de nvidia', baseline=ChatResponse(answer='', sources=[]),
    ))
    assert result.answer == answer


@pytest.mark.parametrize('question', [
    'Qué son los ingresos', 'Define revenue', 'what is EBITDA?', 'WHAT IS EBITDA?',
    'What is the PER?', 'how does an ETF work?', 'Explica la deuda',
    'explícame los ingresos', 'qué es el precio de mercado',
    'qué es la deuda de una empresa', 'what is revenue of a company',
])
def test_generic_concepts_are_available_in_both_languages(question):
    assert _general_scope(question) == 'concept'
    p = StubProvider('Es un concepto financiero general.')
    result = asyncio.run(ChatSynthesisService(p).synthesize_general(
        question=question, baseline=ChatResponse(answer='', sources=[]),
    ))
    assert p.requests and result.model == 'stub'


@pytest.mark.parametrize('question', ['Dame una plantilla para un correo', 'necesito una plantilla de email'])
def test_email_templates_are_ordinary_and_not_labelled_business(question):
    assert _general_scope(question) == 'ordinary'
    p = StubProvider('Asunto: Consulta. Hola, te escribo para consultar un detalle.')
    result = asyncio.run(ChatSynthesisService(p).synthesize_general(
        question=question, baseline=ChatResponse(answer='', sources=[]),
    ))
    assert result.answer == p.text


def test_general_prompt_defines_evidence_labels_and_disallows_fake_currentness():
    prompt = get_prompt('chat_general', allow_remote=False).text
    for term in ['OFICIAL', 'INFERIDO', 'SIN_DATOS', 'no recibes fuentes', 'NO la fecha de una fuente']:
        assert term in prompt
