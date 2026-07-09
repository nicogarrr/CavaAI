import asyncio
import json

import httpx
import pytest

from app.core.config import Settings
from app.llm import (
    AnthropicProvider,
    DisabledProvider,
    GeminiProvider,
    LLMRequest,
    Message,
    OpenAICompatibleProvider,
    ProviderDisabledError,
    ProviderHTTPError,
    TaskModelRouter,
    create_llm_provider,
    parse_json_response,
)


def run(coroutine):
    return asyncio.run(coroutine)


def test_factory_is_deterministically_disabled_without_keys():
    settings = Settings(
        _env_file=None,
        llm_provider="auto",
        openrouter_api_key=None,
        openai_api_key=None,
        anthropic_api_key=None,
        gemini_api_key=None,
    )

    provider = create_llm_provider(settings)

    assert isinstance(provider, DisabledProvider)
    assert provider.reason == "no_api_key_configured"
    with pytest.raises(ProviderDisabledError, match="no_api_key_configured"):
        run(provider.complete(LLMRequest(messages=[Message("user", "Hello")])))


def test_task_router_uses_existing_policy_and_configured_overrides():
    request = LLMRequest(
        messages=[Message("user", "Update the thesis")],
        task="deep_thesis",
        materiality_score=4,
        portfolio_weight=0.01,
    )

    assert (
        TaskModelRouter(
            default_model="default",
            overrides={"thesis_update": "configured-model"},
        ).resolve(request)
        == "configured-model"
    )


def test_openai_compatible_completion_and_structured_output_use_mock_http():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        payload = json.loads(request.content)
        assert request.url == "https://llm.example/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-secret"
        assert payload["model"] == "configured-triage"
        assert payload["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "id": "req-1",
                "model": payload["model"],
                "choices": [
                    {
                        "message": {"content": "```json\n{\"material\": true}\n```"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 8,
                    "completion_tokens": 4,
                    "total_tokens": 12,
                },
            },
        )

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = OpenAICompatibleProvider(
                api_key="test-secret",
                base_url="https://llm.example/v1",
                default_model="default",
                model_overrides={"news_triage": "configured-triage"},
                client=client,
                max_retries=0,
            )
            assert "test-secret" not in repr(provider)
            result = await provider.generate_json(
                LLMRequest(
                    messages=[
                        Message("system", "Classify the item"),
                        Message("user", "A filing was published"),
                    ],
                    task="news_triage",
                )
            )
            return result

    assert run(scenario()) == {"material": True}
    assert len(requests) == 1


def test_anthropic_messages_adapter_uses_mock_http():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.url == "https://api.anthropic.test/v1/messages"
        assert request.headers["x-api-key"] == "anthropic-secret"
        assert request.headers["anthropic-version"] == "2023-06-01"
        assert payload == {
            "model": "claude-test",
            "max_tokens": 200,
            "messages": [{"role": "user", "content": "Summarize"}],
            "system": "Use primary sources",
            "temperature": 0.2,
        }
        return httpx.Response(
            200,
            json={
                "id": "msg-1",
                "model": "claude-test",
                "content": [{"type": "text", "text": "Summary"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 5, "output_tokens": 2},
            },
        )

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = AnthropicProvider(
                api_key="anthropic-secret",
                base_url="https://api.anthropic.test",
                default_model="claude-test",
                client=client,
                max_retries=0,
            )
            return await provider.complete(
                LLMRequest(
                    messages=[
                        Message("system", "Use primary sources"),
                        Message("user", "Summarize"),
                    ],
                    temperature=0.2,
                    max_tokens=200,
                )
            )

    response = run(scenario())
    assert response.text == "Summary"
    assert response.usage.total_tokens == 7
    assert response.provider == "anthropic"


def test_gemini_adapter_and_json_schema_use_mock_http():
    schema = {
        "type": "object",
        "properties": {"score": {"type": "integer"}},
        "required": ["score"],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.url == (
            "https://generativelanguage.test/v1beta/"
            "models/gemini-test%2Fpreview:generateContent"
        )
        assert request.headers["x-goog-api-key"] == "gemini-secret"
        assert payload["systemInstruction"]["parts"][0]["text"] == "Return a score"
        assert payload["contents"][0]["role"] == "user"
        assert payload["generationConfig"]["responseMimeType"] == "application/json"
        assert payload["generationConfig"]["responseSchema"] == schema
        return httpx.Response(
            200,
            headers={"x-goog-request-id": "google-1"},
            json={
                "candidates": [
                    {
                        "content": {"parts": [{"text": "Result:\n{\"score\": 9}"}]},
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 6,
                    "candidatesTokenCount": 3,
                    "totalTokenCount": 9,
                },
            },
        )

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = GeminiProvider(
                api_key="gemini-secret",
                base_url="https://generativelanguage.test/v1beta",
                default_model="gemini-test/preview",
                client=client,
                max_retries=0,
            )
            return await provider.generate_json(
                LLMRequest(
                    messages=[
                        Message("system", "Return a score"),
                        Message("user", "Assess this claim"),
                    ]
                ),
                schema=schema,
                schema_name="assessment",
            )

    assert run(scenario()) == {"score": 9}


def test_errors_and_settings_representations_never_include_keys():
    settings = Settings(
        _env_file=None,
        openrouter_api_key="openrouter-secret",
        openai_api_key="openai-secret",
        anthropic_api_key="anthropic-secret",
        gemini_api_key="gemini-secret",
    )
    settings_repr = repr(settings)
    assert all(
        secret not in settings_repr
        for secret in (
            "openrouter-secret",
            "openai-secret",
            "anthropic-secret",
            "gemini-secret",
        )
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "rejected"})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = OpenAICompatibleProvider(
                api_key="never-leak-this",
                base_url="https://llm.example/v1",
                default_model="test",
                client=client,
                max_retries=0,
            )
            with pytest.raises(ProviderHTTPError) as exc_info:
                await provider.complete(LLMRequest(messages=[Message("user", "Hello")]))
            return str(exc_info.value)

    assert "never-leak-this" not in run(scenario())


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"direct": true}', {"direct": True}),
        ('Before\n```json\n{"fenced": [1, 2]}\n```\nAfter', {"fenced": [1, 2]}),
        ('Explanation first. [{"value": 1}] trailing text', [{"value": 1}]),
    ],
)
def test_parse_json_response_handles_common_model_wrappers(text, expected):
    assert parse_json_response(text) == expected
