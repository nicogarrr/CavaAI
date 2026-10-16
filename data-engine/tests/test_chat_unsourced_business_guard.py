"""Fail closed before generation for business metrics without retrieved evidence."""
import asyncio

import pytest

from app.schemas import ChatResponse
from app.services.chat_synthesis_service import ChatSynthesisService, _general_scope
from app.services.prompt_registry import get_prompt
from tests.test_chat_general_es import StubProvider


@pytest.mark.parametrize('question', [
    'ingresos de Apple 2031', 'empleados de Nvidia',
    'cuántos empleados tiene nvidia', 'Apple revenue in 2031',
    'how many employees does Nvidia have?', 'facturación de apple',
    'ventas de Nvidia', 'beneficio neto de apple', 'deuda de apple',
    'cuál es el flujo de caja de Nvidia', 'cuota de mercado de Apple',
    'proyecta ingresos de Apple para 2031', 'nvidia headcount',
])
def test_business_metrics_never_reach_unrestricted_general_model(question):
    provider = StubProvider('Apple tiene 999999 empleados y ventas de 999 millones.')
    result = asyncio.run(ChatSynthesisService(provider).synthesize_general(
        question=question, baseline=ChatResponse(answer='', sources=[]),
    ))
    assert _general_scope(question) == 'abstain'
    assert provider.requests == []
    assert result.model == 'abstain'
    assert 'SIN_DATOS' in result.answer
    assert '999' not in result.answer
    assert result.sources == []


@pytest.mark.parametrize('answer', [
    'Apple tiene empleados por todo el mundo.',
    'Los ingresos de Nvidia crecen.',
    '[OFICIAL] Nvidia tiene una plantilla enorme.',
    '[INFERIDO] Apple aumentará sus ventas.',
])
def test_business_output_cannot_escape_as_ordinary_chatter(answer):
    service = ChatSynthesisService(StubProvider())
    assert not service._general_output_in_scope(answer, 'ordinary')


def test_general_prompt_names_the_three_evidence_labels_without_claiming_sources():
    prompt = get_prompt('chat_general', allow_remote=False).text
    for label in ['OFICIAL', 'INFERIDO', 'SIN_DATOS']:
        assert label in prompt
    assert 'no recibes fuentes' in prompt
    assert 'futuros' in prompt
