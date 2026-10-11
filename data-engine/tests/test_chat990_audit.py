import asyncio

from app.schemas import ChatResponse
from app.services.budget import BudgetController
from app.services.chat_synthesis_service import ChatSynthesisService
from tests.test_chat_general_es import StubProvider


def test_budget_denied_blocks_first_general_call(monkeypatch):
    monkeypatch.setattr(BudgetController, 'can_spend',lambda *a:False)
    p=StubProvider()
    result=asyncio.run(ChatSynthesisService(p).synthesize_general(question='PER',baseline=ChatResponse(answer='sin datos',sources=[]),db=object()))
    assert p.requests==[]

def test_general_provider_failure_returns_honest_fallback():
    class Broken(StubProvider):
        async def complete(self,request):raise RuntimeError('provider offline')
    result=asyncio.run(ChatSynthesisService(Broken()).synthesize_general(question='PER',baseline=ChatResponse(answer='sin datos',sources=[])))
    assert result.answer

def test_general_rejects_fabricated_citation_and_price():
    p=StubProvider('ASTS cotiza a 999 USD [market_price:999999].')
    result=asyncio.run(ChatSynthesisService(p).synthesize_general(question='precio ASTS',baseline=ChatResponse(answer='sin datos',sources=[])))
    assert '999 USD' not in result.answer

def test_general_english_output_is_not_returned_as_spanish():
    result=asyncio.run(ChatSynthesisService(StubProvider('Hello! The price to earnings ratio is the price divided by earnings.')).synthesize_general(question='que es PER',baseline=ChatResponse(answer='sin datos',sources=[])))
    assert 'Hello!' not in result.answer
