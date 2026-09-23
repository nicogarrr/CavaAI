import asyncio
import json
from decimal import Decimal

import httpx
import pytest

from app.core.config import Settings
from app.llm import (
    DisabledProvider,
    LLMRequest,
    Message,
    MODEL_ALIASES,
    OpenAICompatibleProvider,
    ProviderDisabledError,
    ProviderHTTPError,
    ProviderResponseError,
    TaskModelRouter,
    create_llm_provider,
    parse_json_response,
)
from app.llm.model_aliases import ModelAlias, ModelAliasRegistry
from app.services.llm_router import ModelRoute, ROUTES, route_model, route_table


def run(coroutine):
    return asyncio.run(coroutine)


def test_factory_is_deterministically_disabled_without_opencode_key():
    provider = create_llm_provider(
        Settings(_env_file=None, opencode_go_api_key=None)
    )

    assert isinstance(provider, DisabledProvider)
    assert provider.reason == "opencode_go_api_key_not_configured"
    with pytest.raises(ProviderDisabledError, match="opencode_go_api_key_not_configured"):
        run(provider.complete(LLMRequest(messages=[Message("user", "Hello")])))


def test_factory_only_accepts_opencode_go_and_routes_to_default_model():
    provider = create_llm_provider(
        Settings(
            _env_file=None,
            opencode_go_api_key="test-secret",
            opencode_go_base_url="https://opencode.ai/zen/go/v1",
            opencode_go_model="deepseek-v4-flash",
        )
    )

    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.name == "opencode-go"
    with pytest.raises(ValueError, match="only the OpenCode Go provider"):
        create_llm_provider(
            Settings(
                _env_file=None,
                llm_provider="openrouter",
                opencode_go_api_key="test-secret",
            )
        )


def test_task_router_uses_one_opencode_model_for_every_task():
    assert all(route.model == "deepseek-v4-flash" for route in ROUTES.values())
    assert route_model("deep_thesis").model == "deepseek-v4-flash"
    assert route_model("cheap_extraction").model == "deepseek-v4-flash"
    assert (
        TaskModelRouter(default_model="deepseek-v4-flash")
        .resolve(LLMRequest(messages=[Message("user", "Extract")], task="chat"))
        == "deepseek-v4-flash"
    )


def test_opencode_model_alias_resolves_to_chat_completions_model():
    assert MODEL_ALIASES.resolve(
        "deepseek-v4-flash", provider="opencode-go"
    ) == "deepseek-v4-flash"
    rows = {row["model"]: row for row in route_table()}
    assert rows["deepseek-v4-flash"]["provider"] == "opencode-go"
    assert rows["deepseek-v4-flash"]["provider_model_id"] == "deepseek-v4-flash"


def test_active_route_validation_rejects_other_providers():
    with pytest.raises(ValueError, match="not active provider"):
        MODEL_ALIASES.validate_active_routes(
            [ModelRoute("broken", "deepseek-v4-flash", "test")],
            provider="openrouter",
        )

    disabled = ModelAlias(
        internal_alias="disabled-model",
        provider="opencode-go",
        provider_model_id="disabled-model",
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
            provider="opencode-go",
        )


def test_opencode_go_completion_uses_chat_completions_endpoint():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.url == "https://opencode.test/zen/go/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-secret"
        assert payload["model"] == "deepseek-v4-flash"
        return httpx.Response(
            200,
            json={
                "id": "opencode-request",
                "model": "deepseek-v4-flash",
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
                    opencode_go_api_key="test-secret",
                    opencode_go_base_url="https://opencode.test/zen/go/v1",
                ),
                client=client,
            )
            return await provider.complete(
                LLMRequest(messages=[Message("user", "Extract")], task="chat")
            )

    assert run(scenario()).text == "ok"


def test_openai_compatible_provider_rejects_missing_usage():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "deepseek-v4-flash",
                "choices": [
                    {"message": {"content": "ok"}, "finish_reason": "stop"}
                ],
            },
        )

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = OpenAICompatibleProvider(
                api_key="test-secret",
                base_url="https://opencode.test/zen/go/v1",
                default_model="deepseek-v4-flash",
                provider_name="opencode-go",
                client=client,
                max_retries=0,
            )
            return await provider.complete(
                LLMRequest(messages=[Message("user", "Extract")])
            )

    with pytest.raises(ProviderResponseError, match="missing token usage"):
        run(scenario())


def test_openai_compatible_provider_rejects_incomplete_usage():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "deepseek-v4-flash",
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {"completion_tokens": 1},
            },
        )

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = OpenAICompatibleProvider(
                api_key="test-secret",
                base_url="https://opencode.test/zen/go/v1",
                default_model="deepseek-v4-flash",
                provider_name="opencode-go",
                client=client,
                max_retries=0,
            )
            return await provider.complete(LLMRequest(messages=[Message("user", "Extract")]))

    with pytest.raises(ProviderResponseError, match="invalid prompt token usage"):
        run(scenario())


def test_openai_compatible_provider_caps_requested_max_tokens():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["max_tokens"] == 8
        return httpx.Response(
            200,
            json={
                "model": "deepseek-v4-flash",
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
            provider = OpenAICompatibleProvider(
                api_key="test-secret",
                base_url="https://opencode.test/zen/go/v1",
                default_model="deepseek-v4-flash",
                provider_name="opencode-go",
                client=client,
                max_retries=0,
                max_output_tokens=8,
            )
            return await provider.complete(
                LLMRequest(
                    messages=[Message("user", "Extract")],
                    max_tokens=1_000_000,
                )
            )

    assert run(scenario()).text == "ok"


def test_structured_output_uses_openai_compatible_contract():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["model"] == "deepseek-v4-flash"
        assert payload["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "id": "structured-request",
                "model": payload["model"],
                "choices": [
                    {
                        "message": {"content": '{"material": true}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = OpenAICompatibleProvider(
                api_key="test-secret",
                base_url="https://opencode.test/zen/go/v1",
                default_model="deepseek-v4-flash",
                provider_name="opencode-go",
                client=client,
                max_retries=0,
            )
            return await provider.generate_json(
                LLMRequest(messages=[Message("user", "Classify")])
            )

    assert run(scenario()) == {"material": True}


def test_settings_and_errors_never_include_api_keys():
    settings = Settings(_env_file=None, opencode_go_api_key="opencode-secret")
    assert "opencode-secret" not in repr(settings)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "rejected"})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = OpenAICompatibleProvider(
                api_key="never-leak-this",
                base_url="https://opencode.test/zen/go/v1",
                default_model="deepseek-v4-flash",
                provider_name="opencode-go",
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
