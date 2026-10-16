import asyncio

import pytest

from app.services.chat_service import ChatService
from tests.test_chat_general_es import StubProvider, _db


@pytest.mark.parametrize(('question', 'fragment'), [
    ('gracias', 'De nada'), ('Muchas gracias!', 'De nada'),
    ('adiós', 'Hasta luego'), ('ADIOS!', 'Hasta luego'),
    ('hasta luego', 'Hasta luego'), ('ok', 'De acuerdo'), ('vale.', 'De acuerdo'),
])
def test_short_replies_match_their_category_without_llm(question, fragment):
    provider = StubProvider()
    response = asyncio.run(ChatService(provider).answer(_db(), question, 'portfolio', None))
    assert response.model == 'small-talk'
    assert fragment in response.answer
    assert 'Soy el asistente' not in response.answer
    assert provider.requests == []
    assert response.sources == []


@pytest.mark.parametrize('question', ['hola', '¿Qué tal?', '¿Cómo estás?', 'buenos días'])
def test_greetings_are_recognized_with_accents(question):
    provider = StubProvider()
    response = asyncio.run(ChatService(provider).answer(_db(), question, 'portfolio', None))
    assert response.model == 'small-talk'
    assert 'CavaAI' in response.answer
    assert provider.requests == []


def test_long_whitespace_input_is_not_small_talk_and_does_not_backtrack_quadratically():
    import time

    from app.services.chat_service import _SMALL_TALK_RE

    start = time.monotonic()
    assert _SMALL_TALK_RE.match(" " * 200000 + "x") is None
    assert time.monotonic() - start < 1.0
