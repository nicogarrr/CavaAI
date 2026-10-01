"""Tool calling real en el adaptador OpenAI-compatible.

Evidencia del proveedor (verificada 2026-10-01):
- https://opencode.ai/docs/zen lista `space-bunny-free` en
  `https://opencode.ai/zen/v1/chat/completions` con el paquete
  `@ai-sdk/openai-compatible`, es decir, el sobre OpenAI Chat Completions
  completo, `tools` incluido.
- El catalogo que OpenCode usa (models.dev, provider `opencode`) marca
  `tool_call: true` y `reasoning: true` para `space-bunny-free`.

Por eso la capacidad declarada en `model_aliases.py` era CIERTA y el defecto
estaba en el codigo, que no la implementaba. Estos tests pinning el extremo de
las dos puntas: `tools` sale en el sobre y `tool_calls` vuelve parseado y
validado; y ninguna ruta afirma una capacidad que el adaptador no haga.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.llm import (
    ADAPTER_CAPABILITIES,
    TOOL_CALLING,
    LLMRequest,
    Message,
    OpenAICompatibleProvider,
    ProviderRequestError,
    ProviderResponseError,
    ResponseFormat,
    ToolCall,
    ToolDefinition,
    parse_tool_calls,
)
from app.llm.model_aliases import MODEL_ALIASES
from app.services.llm_router import ROUTES, route_table, unsupported_routes

READ_ONLY_TOOL = ToolDefinition(
    name="read_filing_section",
    description="Read one bounded, already-ingested filing section.",
    parameters={
        "type": "object",
        "properties": {"chunk_id": {"type": "string"}},
        "required": ["chunk_id"],
        "additionalProperties": False,
    },
)


def run(coroutine):
    return asyncio.run(coroutine)


def _provider(handler, **kwargs) -> OpenAICompatibleProvider:
    transport = httpx.MockTransport(handler)
    return OpenAICompatibleProvider(
        api_key="test-secret",
        base_url="https://opencode.test/zen/v1",
        default_model="space-bunny-free",
        provider_name="opencode-go",
        client=httpx.AsyncClient(transport=transport),
        max_retries=0,
        **kwargs,
    )


def _body(message: dict, *, finish_reason: str = "tool_calls") -> dict:
    return {
        "id": "req-1",
        "model": "space-bunny-free",
        "choices": [{"message": message, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
    }


# ---------------------------------------------------------------------------
# Envio: tools/tool_choice solo si la capacidad esta implementada
# ---------------------------------------------------------------------------


def test_tools_and_tool_choice_reach_the_wire():
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            json=_body(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "read_filing_section",
                                "arguments": '{"chunk_id": "c-42"}',
                            },
                        }
                    ],
                }
            ),
        )

    provider = _provider(handler)
    response = run(
        provider.complete(
            LLMRequest(
                messages=[Message("user", "Read chunk c-42")],
                task="tool_workflow",
                tools=[READ_ONLY_TOOL],
                tool_choice="required",
            )
        )
    )

    assert seen[0]["tools"] == [READ_ONLY_TOOL.to_openai()]
    assert seen[0]["tool_choice"] == "required"
    assert response.has_tool_calls
    assert response.text == ""


def test_named_tool_choice_is_normalised_to_openai_shape():
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            json=_body(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {"function": {"name": "read_filing_section", "arguments": "{}"}}
                    ],
                }
            ),
        )

    provider = _provider(handler)
    run(
        provider.complete(
            LLMRequest(
                messages=[Message("user", "Read")],
                tools=[READ_ONLY_TOOL],
                tool_choice={"type": "function", "function": {"name": "read_filing_section"}},
            )
        )
    )
    assert seen[0]["tool_choice"] == {
        "type": "function",
        "function": {"name": "read_filing_section"},
    }


def test_no_tools_means_no_tool_fields_on_the_wire():
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            json=_body({"role": "assistant", "content": "ok"}, finish_reason="stop"),
        )

    provider = _provider(handler)
    run(provider.complete(LLMRequest(messages=[Message("user", "Hello")])))
    assert "tools" not in seen[0]
    assert "tool_choice" not in seen[0]


def test_declaring_tools_without_the_capability_fails_before_any_http_call():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        calls.append(request)
        raise AssertionError("no debe llamar al proveedor")

    provider = _provider(handler)
    # Simula el defecto original: el adaptador que declara no implementar tools.
    provider.supported_capabilities = frozenset({"text", "structured_output"})
    with pytest.raises(ProviderRequestError, match="does not implement tool calling"):
        run(
            provider.complete(
                LLMRequest(messages=[Message("user", "Read")], tools=[READ_ONLY_TOOL])
            )
        )
    assert calls == []


def test_tool_choice_without_tools_is_rejected():
    with pytest.raises(ValueError, match="requires at least one tool"):
        LLMRequest(messages=[Message("user", "Hi")], tool_choice="auto")


def test_tool_choice_naming_an_unregistered_function_is_rejected():
    with pytest.raises(ValueError, match="not in tools"):
        LLMRequest(
            messages=[Message("user", "Hi")],
            tools=[READ_ONLY_TOOL],
            tool_choice={"type": "function", "function": {"name": "write_database"}},
        )


def test_duplicate_tool_names_are_rejected():
    with pytest.raises(ValueError, match="unique"):
        LLMRequest(messages=[Message("user", "Hi")], tools=[READ_ONLY_TOOL, READ_ONLY_TOOL])


# ---------------------------------------------------------------------------
# Parseo: tolerante en la forma, estricto en lo que no se puede inventar
# ---------------------------------------------------------------------------


def test_parse_valid_tool_calls():
    calls = parse_tool_calls(
        [
            {
                "id": "call_a",
                "type": "function",
                "function": {"name": "read_filing_section", "arguments": '{"chunk_id": "c-1"}'},
            },
            {
                "id": "call_b",
                "type": "function",
                "function": {"name": "other", "arguments": '{"a": 1, "b": [2]}'},
            },
        ]
    )
    assert calls == (
        ToolCall(id="call_a", name="read_filing_section", arguments={"chunk_id": "c-1"}),
        ToolCall(id="call_b", name="other", arguments={"a": 1, "b": [2]}),
    )
    assert isinstance(calls[0].arguments, dict)


def test_parse_accepts_already_decoded_arguments_and_empty_string():
    assert parse_tool_calls([{"function": {"name": "t", "arguments": {"x": 1}}}])[0].arguments == {
        "x": 1
    }
    assert parse_tool_calls([{"function": {"name": "t", "arguments": ""}}])[0].arguments == {}
    assert parse_tool_calls([{"function": {"name": "t"}}])[0].arguments == {}
    # Falta el envoltorio `function` (proveedor con otra forma).
    assert parse_tool_calls([{"name": "t", "arguments": '{"x": 2}'}])[0].arguments == {"x": 2}


def test_parse_synthesises_missing_call_id():
    call = parse_tool_calls([{"function": {"name": "t", "arguments": "{}"}}])[0]
    assert call.id


def test_no_tool_calls_returns_empty_tuple():
    assert parse_tool_calls(None) == ()
    assert parse_tool_calls([]) == ()


def test_invalid_json_in_tool_arguments_is_an_error_not_a_silent_drop():
    with pytest.raises(ProviderResponseError, match="invalid JSON"):
        parse_tool_calls([{"id": "c", "function": {"name": "t", "arguments": "{not json"}}])


def test_non_object_tool_arguments_is_an_error():
    with pytest.raises(ProviderResponseError, match="non-object arguments"):
        parse_tool_calls([{"function": {"name": "t", "arguments": "[1, 2]"}}])


def test_tool_call_without_a_name_is_an_error():
    with pytest.raises(ProviderResponseError, match="without a name"):
        parse_tool_calls([{"id": "c", "function": {"arguments": "{}"}}])


def test_malformed_tool_call_envelope_is_an_error():
    with pytest.raises(ProviderResponseError, match="malformed tool call"):
        parse_tool_calls(["read_filing_section"])
    with pytest.raises(ProviderResponseError, match="invalid tool calls"):
        parse_tool_calls({"function": {}})


def test_response_without_tool_calls_keeps_plain_text():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_body({"role": "assistant", "content": "solo texto"}, finish_reason="stop"),
        )

    provider = _provider(handler)
    response = run(provider.complete(LLMRequest(messages=[Message("user", "Hi")])))
    assert response.text == "solo texto"
    assert response.tool_calls == ()
    assert not response.has_tool_calls


def test_tool_call_response_with_invalid_arguments_raises_from_the_provider():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_body(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {"id": "c", "function": {"name": "t", "arguments": "{"}}
                    ],
                }
            ),
        )

    provider = _provider(handler)
    with pytest.raises(ProviderResponseError, match="invalid JSON"):
        run(provider.complete(LLMRequest(messages=[Message("user", "Hi")])))


def test_text_and_tool_calls_can_coexist():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_body(
                {
                    "role": "assistant",
                    "content": "Voy a mirar ese chunk.",
                    "tool_calls": [{"function": {"name": "t", "arguments": "{}"}}],
                }
            ),
        )

    provider = _provider(handler)
    response = run(provider.complete(LLMRequest(messages=[Message("user", "Hi")])))
    assert response.text == "Voy a mirar ese chunk."
    assert response.tool_calls[0].name == "t"


def test_empty_message_without_tool_calls_is_still_an_error():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_body({"role": "assistant", "content": ""}, finish_reason="stop"),
        )

    provider = _provider(handler)
    with pytest.raises(ProviderResponseError, match="empty assistant message"):
        run(provider.complete(LLMRequest(messages=[Message("user", "Hi")])))


def test_structured_output_still_goes_out_with_tools():
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            json=_body(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{"function": {"name": "t", "arguments": "{}"}}],
                }
            ),
        )

    provider = _provider(handler)
    run(
        provider.complete(
            LLMRequest(
                messages=[Message("user", "Hi")],
                tools=[READ_ONLY_TOOL],
                response_format=ResponseFormat.json_object(),
            )
        )
    )
    assert seen[0]["response_format"] == {"type": "json_object"}
    assert seen[0]["tools"] == [READ_ONLY_TOOL.to_openai()]


def test_tool_call_arguments_are_always_a_mapping_not_raw_text():
    with pytest.raises(TypeError, match="not raw text"):
        ToolCall(id="c", name="t", arguments='{"a": 1}')  # type: ignore[arg-type]


def test_input_messages_still_require_content():
    with pytest.raises(ValueError, match="non-empty string"):
        Message("user", "   ")


# ---------------------------------------------------------------------------
# Coherencia capacidad declarada vs capacidad implementada
# ---------------------------------------------------------------------------


def test_declared_capabilities_are_actually_implemented_by_the_adapter():
    """Falla si ADAPTER_CAPABILITIES afirma algo que el adaptador no hace.

    Se comprueba el extremo de las dos puntas, no solo el conjunto: cada
    capacidad declarada tiene un comportamiento observable en el sobre.
    """
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            json=_body(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{"function": {"name": "t", "arguments": "{}"}}],
                }
            ),
        )

    provider = _provider(
        handler,
        reasoning_effort="max",
        reasoning_effort_models={"space-bunny-free"},
    )
    run(
        provider.complete(
            LLMRequest(
                messages=[Message("user", "Hi")],
                tools=[READ_ONLY_TOOL],
                response_format=ResponseFormat.json_object(),
            )
        )
    )
    payload = seen[0]
    assert "text" in provider.supported_capabilities
    assert "structured_output" in provider.supported_capabilities
    assert "reasoning" in provider.supported_capabilities
    assert TOOL_CALLING in provider.supported_capabilities
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["reasoning_effort"] == "max"
    assert payload["tools"]


def test_capabilities_the_adapter_does_not_implement_are_not_claimed():
    """Ni multimodalidad, ni streaming, ni cache de prompts del proveedor."""
    assert "image" not in ADAPTER_CAPABILITIES
    assert "video" not in ADAPTER_CAPABILITIES
    assert "streaming" not in ADAPTER_CAPABILITIES


def test_every_alias_used_by_an_active_route_is_backed_by_the_adapter():
    """El registro no puede afirmar mas que el codigo (y al reves, tampoco)."""
    for route in ROUTES.values():
        alias = MODEL_ALIASES.get(route.model)
        assert alias is not None, route.task
        assert alias.supported_capabilities <= ADAPTER_CAPABILITIES, (
            f"{route.task} declara capacidades que el adaptador no implementa: "
            f"{sorted(alias.supported_capabilities - ADAPTER_CAPABILITIES)}"
        )


def test_no_route_requires_a_capability_the_adapter_lacks():
    assert unsupported_routes(ADAPTER_CAPABILITIES) == []


def test_tool_routes_are_reported_as_unsupported_without_tool_calling():
    """El defecto original se hace visible en vez de quedar oculto."""
    unsupported = unsupported_routes({"text", "structured_output"})
    assert unsupported == ["agentic_red_team", "tool_workflow"]


def test_route_table_exposes_required_capabilities():
    rows = {row["task"]: row for row in route_table()}
    assert rows["tool_workflow"]["required_capabilities"] == ["tool_calling"]
    assert rows["chat"]["required_capabilities"] == ["text"]