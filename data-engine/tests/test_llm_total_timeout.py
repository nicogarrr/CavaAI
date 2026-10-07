import asyncio

import httpx
import pytest

from app.core.config import Settings
from app.llm import LLMRequest, Message, create_llm_provider
from app.llm.errors import ProviderTransportError

BODY = {
    "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
}


def _settings(**kw):
    return Settings(
        _env_file=None,
        opencode_go_api_key="test-secret",
        opencode_go_base_url="https://opencode.test/zen/go/v1",
        **kw,
    )


def test_total_timeout_caps_hung_provider_including_retries():
    async def handler(_request):
        await asyncio.sleep(5)
        return httpx.Response(200, json=BODY)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = create_llm_provider(
                _settings(llm_total_timeout_seconds=0.2, llm_timeout_seconds=30), client=client
            )
            await provider.complete(LLMRequest(messages=[Message("user", "x")], cache=False))

    with pytest.raises(ProviderTransportError) as exc:
        asyncio.run(asyncio.wait_for(scenario(), timeout=3))
    assert exc.value.reason == "timeout"


def test_hidden_reasoning_model_gets_output_token_floor():
    seen = {}

    def handler(request):
        import json

        seen["max_tokens"] = json.loads(request.content)["max_tokens"]
        return httpx.Response(200, json=BODY)

    async def scenario(model):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = create_llm_provider(_settings(), client=client)
            await provider.complete(
                LLMRequest(messages=[Message("user", "x")], model=model, max_tokens=80, cache=False)
            )

    asyncio.run(scenario("longcat-2.5-preview-free"))
    assert seen["max_tokens"] == 1024
    asyncio.run(scenario("some-other-model"))
    assert seen["max_tokens"] == 80
