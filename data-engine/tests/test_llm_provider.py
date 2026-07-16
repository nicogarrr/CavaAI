import asyncio
import json
from decimal import Decimal

import httpx
import pytest

from app.core.config import Settings
from app.llm import (
    AnthropicProvider,
    DisabledProvider,
    GeminiProvider,
    LLMRequest,
    MODEL_ALIASES,
    Message,
    OpenAICompatibleProvider,
    ProviderDisabledError,
    ProviderHTTPError,
    TaskModelRouter,
    create_llm_provider,
    parse_json_response,
)
from app.llm.model_aliases import ModelAlias, ModelAliasRegistry
from app.services.llm_router import ModelRoute, ROUTES, route_model, route_table


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
    assert provider.reason == "openrouter_api_key_not_configured"
    with pytest.raises(ProviderDisabledError, match="openrouter_api_key_not_configured"):
        run(provider.complete(LLMRequest(messages=[Message("user", "Hello")])))


def test_auto_policy_does_not_fall_back_to_unregistered_provider_aliases():
    provider = create_llm_provider(
        Settings(
            _env_file=None,
            llm_provider="auto",
            openrouter_api_key=None,
            openai_api_key="configured-but-not-selected",
        )
    )

    assert isinstance(provider, DisabledProvider)
    assert provider.reason == "openrouter_api_key_not_configured"


def test_explicit_non_openrouter_provider_requires_complete_task_overrides():
    with pytest.raises(ValueError, match="requires model overrides for every active task"):
        create_llm_provider(
            Settings(
                _env_file=None,
                llm_provider="openai",
                openai_api_key="test-secret",
            )
        )

    provider = create_llm_provider(
        Settings(
            _env_file=None,
            llm_provider="openai",
            openai_api_key="test-secret",
            llm_model_overrides={route.task: "gpt-4o-mini" for route in ROUTES.values()},
        )
    )
    assert isinstance(provider, OpenAICompatibleProvider)


def test_task_router_uses_existing_policy_and_configured_overrides():
    request = LLMRequest(
        messages=[Message("user", "Update the thesis")],
        task="deep_thesis",
        materiality_score=4,
        portfolio_weight=0.01,
    )

    assert route_model("cheap_extraction").model == "qwen-flash"
    assert route_model("main_financial_analysis").model == "qwen3.7-plus"
    assert route_model("agentic_red_team").model == "glm-5.2"

    assert (
        TaskModelRouter(
            default_model="default",
            overrides={"thesis_update": "configured-model"},
        ).resolve(request)
        == "configured-model"
    )


def test_internal_model_aliases_resolve_to_real_openrouter_ids():
    expected = {
        "qwen-flash": "qwen/qwen3.6-flash",
        "qwen3.7-plus": "qwen/qwen3.7-plus",
        "glm-5.2": "z-ai/glm-5.2",
        "qwen3.7-max": "qwen/qwen3.7-max",
        "kimi-k2.7-code": "moonshotai/kimi-k2.7-code",
        "deepseek-v4-flash": "deepseek/deepseek-v4-flash",
    }

    assert {
        alias: MODEL_ALIASES.resolve(alias, provider="openrouter")
        for alias in expected
    } == expected
    assert TaskModelRouter(
        default_model="qwen-flash",
        provider="openrouter",
    ).resolve(LLMRequest(messages=[Message("user", "Extract")], task="cheap_extraction")) == (
        "qwen/qwen3.6-flash"
    )

    rows = {row["model"]: row for row in route_table()}
    assert rows["qwen3.7-plus"]["provider_model_id"] == "qwen/qwen3.7-plus"
    assert rows["glm-5.2"]["context_window"] == 1_048_576


def test_active_route_validation_fails_for_unknown_or_wrong_provider_models():
    with pytest.raises(ValueError, match="unknown model alias"):
        MODEL_ALIASES.validate_active_routes(
            [ModelRoute("broken", "does-not-exist", "test")],
            provider="openrouter",
        )

    with pytest.raises(ValueError, match="not active provider"):
        MODEL_ALIASES.validate_active_routes(
            [ROUTES["chat"]],
            provider="anthropic",
        )

    disabled = ModelAlias(
        internal_alias="disabled-model",
        provider="openrouter",
        provider_model_id="vendor/disabled-model",
        enabled=False,
        context_window=1,
        input_cost=Decimal("0"),
        output_cost=Decimal("0"),
        supported_capabilities=frozenset({"text"}),
    )
    registry = ModelAliasRegistry([disabled])
    with pytest.raises(ValueError, match="is disabled"):
        registry.validate_active_routes(
            [ModelRoute("disabled", "disabled-model", "test")],
            provider="openrouter",
        )


def test_factory_sends_provider_model_id_instead_of_internal_alias():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["model"] == "qwen/qwen3.6-flash"
        return httpx.Response(
            200,
            json={
                "id": "alias-request",
                "model": payload["model"],
                "choices": [
                    {"message": {"content": "ok"}, "finish_reason": "stop"}
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            },
        )

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = create_llm_provider(
                Settings(
                    _env_file=None,
                    llm_provider="openrouter",
                    openrouter_api_key="test-secret",
                ),
                client=client,
            )
            return await provider.complete(
                LLMRequest(
                    messages=[Message("user", "Extract")],
                    task="cheap_extraction",
                )
            )

    assert run(scenario()).model == "qwen/qwen3.6-flash"

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
