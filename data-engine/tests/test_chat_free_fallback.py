import asyncio
from functools import wraps

import httpx
import pytest

from app.core.config import Settings
from app.llm.chat_provider import GROQ_MODEL, ChatFallbackProvider, create_chat_llm_provider
from app.llm.contracts import LLMRequest, LLMResponse, Message, Usage
from app.llm.errors import ProviderHTTPError, ProviderRequestError, ProviderTransportError


def run_async(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        return asyncio.run(fn(*args, **kwargs))
    return wrapped


def response(text="válida", *, model="primary", provider="opencode-go", finish="stop"):
    return LLMResponse(Message("assistant", text), Usage(), model, provider, finish_reason=finish)


class Fake:
    name = "fake"
    supported_capabilities = frozenset({"text", "structured_output"})
    model_router = None
    def __init__(self, value=None, delay=0):
        self.value = value or response()
        self.delay = delay
        self.calls = []
        self.cancelled = False
    async def complete(self, request):
        self.calls.append(request)
        try:
            await asyncio.sleep(self.delay)
            if isinstance(self.value, Exception): raise self.value
            return self.value
        except asyncio.CancelledError:
            self.cancelled = True
            raise


@run_async
async def test_fast_primary_never_calls_backup():
    p, b = Fake(), Fake()
    out = await ChatFallbackProvider(p, b, total=.3, delay=.1).complete(LLMRequest([Message("user", "hola")], task="chat"))
    assert out.provider == "opencode-go" and not b.calls


@run_async
async def test_429_uses_independent_provider_with_pinned_model():
    p, b = Fake(ProviderHTTPError("opencode-go", 429)), Fake(response(model=GROQ_MODEL, provider="groq"))
    out = await ChatFallbackProvider(p, b, total=.3, delay=.1).complete(LLMRequest([Message("user", "hola")], task="chat", model="deepseek-v4.1-flash-free"))
    assert out.provider == "groq" and b.calls[0].model == GROQ_MODEL


@run_async
async def test_slow_primary_remains_eligible_and_backup_cancelled():
    p, b = Fake(delay=.08), Fake(delay=.2)
    out = await ChatFallbackProvider(p, b, total=.3, delay=.03).complete(LLMRequest([Message("user", "hola")], task="chat"))
    assert out.provider == "opencode-go" and b.cancelled


@run_async
async def test_backup_wins_then_primary_is_cancelled():
    p, b = Fake(delay=.2), Fake(response(model=GROQ_MODEL, provider="groq"))
    out = await ChatFallbackProvider(p, b, total=.3, delay=.01).complete(LLMRequest([Message("user", "hola")], task="chat"))
    assert out.provider == "groq" and p.cancelled


@run_async
async def test_deadline_cancels_both():
    p, b = Fake(delay=1), Fake(delay=1)
    with pytest.raises(ProviderTransportError):
        await ChatFallbackProvider(p, b, total=.05, delay=.01).complete(LLMRequest([Message("user", "hola")], task="chat"))
    assert p.cancelled and b.cancelled


@run_async
async def test_our_request_error_does_not_trigger_another_provider():
    p, b = Fake(ProviderRequestError("invalid")), Fake()
    with pytest.raises(ProviderRequestError):
        await ChatFallbackProvider(p, b).complete(LLMRequest([Message("user", "hola")], task="chat"))
    assert not b.calls


@run_async
async def test_nonchat_task_never_calls_groq():
    p, b = Fake(), Fake()
    await ChatFallbackProvider(p, b).complete(LLMRequest([Message("user", "hola")], task="deep_thesis"))
    assert not b.calls


@run_async
async def test_truncated_primary_does_not_win_over_valid_backup():
    p, b = Fake(response(finish="length")), Fake(response(model=GROQ_MODEL, provider="groq"))
    out = await ChatFallbackProvider(p, b).complete(LLMRequest([Message("user", "hola")], task="chat"))
    assert out.provider == "groq"


@pytest.mark.parametrize("missing", ["groq_api_key", "groq_free_plan_confirmed", "groq_zdr_confirmed"])
def test_factory_is_fail_closed(missing):
    cfg = dict(llm_enabled=True, opencode_go_api_key="synthetic", groq_api_key="synthetic", groq_chat_fallback_enabled=True, groq_free_plan_confirmed=True, groq_zdr_confirmed=True)
    cfg[missing] = None if missing.endswith("key") else False
    with pytest.raises(ValueError, match="verified free plan"):
        create_chat_llm_provider(Settings(**cfg))


@run_async
async def test_real_adapter_envelope_is_groq_not_deepseek():
    seen = []
    def handler(req):
        import json
        body = json.loads(req.content)
        seen.append(body)
        if req.url.host == "primary.invalid": return httpx.Response(429)
        assert req.url.host == "api.groq.com"
        assert req.headers["user-agent"] == "cavaai/1.0"
        assert body["model"] == GROQ_MODEL and body["reasoning_effort"] == "low"
        return httpx.Response(200, json={"model": GROQ_MODEL, "choices": [{"message": {"role": "assistant", "content": "Respuesta factual"}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        cfg = Settings(llm_enabled=True, opencode_go_api_key="synthetic", opencode_go_base_url="https://primary.invalid/v1", llm_max_retries=0, groq_api_key="synthetic", groq_chat_fallback_enabled=True, groq_free_plan_confirmed=True, groq_zdr_confirmed=True)
        out = await create_chat_llm_provider(cfg, client=client).complete(LLMRequest([Message("user", "hola")], task="chat"))
    assert out.provider == "groq" and len(seen) == 2


@run_async
async def test_backup_failure_still_allows_slow_valid_primary():
    p, b = Fake(delay=.08), Fake(ProviderHTTPError("groq", 429))
    out = await ChatFallbackProvider(p, b, total=.3, delay=.01).complete(LLMRequest([Message("user", "hola")], task="chat"))
    assert out.provider == "opencode-go"


@run_async
async def test_external_cancel_collects_both_tasks():
    p, b = Fake(delay=1), Fake(delay=1)
    task = asyncio.create_task(ChatFallbackProvider(p, b, total=2, delay=.01).complete(LLMRequest([Message("user", "hola")], task="chat")))
    await asyncio.sleep(.03)
    task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    assert p.cancelled and b.cancelled


@run_async
async def test_backup_receives_financial_advice_boundary():
    p, b = Fake(ProviderHTTPError("opencode-go", 429)), Fake()
    await ChatFallbackProvider(p, b).complete(LLMRequest([Message("user", "hola")], task="chat"))
    assert "No des asesoramiento financiero personalizado" in b.calls[0].messages[-1].content


@run_async
async def test_tools_never_go_to_backup():
    from app.llm.contracts import ToolDefinition
    p, b = Fake(), Fake()
    await ChatFallbackProvider(p, b).complete(LLMRequest([Message("user", "hola")], task="chat", tools=(ToolDefinition("read"),)))
    assert not b.calls


def test_disabled_flag_keeps_primary_unchanged():
    provider = create_chat_llm_provider(Settings(llm_enabled=True, opencode_go_api_key="synthetic"))
    assert provider.name == "opencode-go"


@run_async
async def test_paid_primary_override_rejected_before_network():
    seen = []
    def handler(req):
        seen.append(req)
        raise AssertionError("network must not run")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        cfg = Settings(llm_enabled=True, opencode_go_api_key="synthetic", opencode_go_model="paid-unknown", llm_model_overrides={"chat": "paid-unknown"}, groq_api_key="synthetic", groq_chat_fallback_enabled=True, groq_free_plan_confirmed=True, groq_zdr_confirmed=True)
        with pytest.raises(ProviderRequestError, match="not verified free"):
            await create_chat_llm_provider(cfg, client=client).complete(LLMRequest([Message("user", "hola")], task="chat"))
    assert not seen


@pytest.mark.parametrize("text", [
    "Para tu cartera, te recomiendo comprar más AAA y vender BBB.",
    "Para su jubilación, adquiera acciones de AAA y liquide la posición en BBB.",
    "You should buy AAA and sell BBB.", "Asigne un 60% a acciones.",
])
@run_async
async def test_known_advice_canaries_rejected(text):
    from app.llm.errors import ProviderResponseError
    p, b = Fake(ProviderHTTPError("opencode-go", 429)), Fake(response(text, model=GROQ_MODEL, provider="groq"))
    with pytest.raises(ProviderResponseError, match="educational boundary"):
        await ChatFallbackProvider(p, b).complete(LLMRequest([Message("user", "sintético")], task="chat"))


@run_async
async def test_structured_context_backup_is_explicit_and_preserved():
    p, b = Fake(ProviderHTTPError("opencode-go", 429)), Fake(response("Datos sintéticos de la prueba.", model=GROQ_MODEL, provider="groq"))
    req = LLMRequest([Message("system", "Contrato estructurado"), Message("user", "Pregunta, ticker AAA, secciones y fuentes SINTÉTICAS")], task="main_financial_analysis")
    out = await ChatFallbackProvider(p, b).complete(req)
    assert out.provider == "groq"
    assert tuple(b.calls[0].messages[:-1]) == tuple(req.messages)
    assert "No des asesoramiento financiero personalizado" in b.calls[0].messages[-1].content

@pytest.mark.parametrize("bad", ["not_json", "citation", "language"])
@run_async
async def test_invalid_fast_backup_keeps_valid_slow_primary_through_synthesis(bad):
    import json

    from app.services.chat_synthesis_service import ChatSynthesisService
    from tests.test_chat_synthesis_service import _baseline, _llm_payload
    payload = _llm_payload()
    valid = json.dumps(payload)
    if bad == "not_json":
        invalid = "Texto español correcto pero no JSON"
    elif bad == "citation":
        invalid = json.dumps(_llm_payload(citations=["financial_fact:999"]))
    else:
        for section in payload["sections"]:
            section["body"] = "The company is profitable and the earnings are growing because the market is strong."
        invalid = json.dumps(payload)
    p = Fake(response(valid, model="valid-primary"), delay=.08)
    b = Fake(response(invalid, model=GROQ_MODEL, provider="groq"), delay=.01)
    provider = ChatFallbackProvider(p, b, total=.4, delay=.001)
    result = await ChatSynthesisService(provider).synthesize(
        question="Resumen sintético", ticker="AAA", baseline=_baseline(), enable_debate=False,
    )
    assert result.model == "valid-primary"
    assert result.llm_trace["citation_verification"] is True
    assert not p.cancelled and b.calls


@run_async
async def test_invalid_fast_general_backup_preserves_valid_slow_primary():
    from app.schemas import ChatResponse
    from app.services.chat_synthesis_service import ChatSynthesisService
    p = Fake(response("Respuesta breve en español.", model="valid-primary"), delay=.08)
    b = Fake(response("The company is profitable and the earnings are growing.", model=GROQ_MODEL, provider="groq"), delay=.01)
    result = await ChatSynthesisService(ChatFallbackProvider(p, b, total=.4, delay=.001)).synthesize_general(
        question="Cuéntame algo", baseline=ChatResponse(answer="", sources=[]),
    )
    assert result.model == "valid-primary" and not p.cancelled


def test_candidate_validation_context_is_per_call_not_shared():
    provider = ChatFallbackProvider(Fake(), Fake())
    a = provider.with_candidate_validator(lambda r: None)
    b = provider.with_candidate_validator(lambda r: None)
    assert a is not b and a.validator is not b.validator and provider.validator is None
