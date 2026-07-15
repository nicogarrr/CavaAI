from __future__ import annotations

import json
from typing import Any, Mapping
from urllib.parse import quote

import httpx

from app.llm.base import LLMProvider
from app.llm.contracts import LLMRequest, LLMResponse, Message, MessageRole, Usage
from app.llm.errors import ProviderDisabledError, ProviderRequestError, ProviderResponseError
from app.llm.routing import TaskModelRouter


def _integer(value: Any) -> int:
    return value if isinstance(value, int) and value >= 0 else 0


def _join_text_blocks(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        )
    return ""


class DisabledProvider(LLMProvider):
    name = "disabled"

    def __init__(self, reason: str = "no_provider_configured") -> None:
        self.reason = reason
        super().__init__(
            model_router=TaskModelRouter(default_model="disabled"),
            timeout_seconds=1,
            max_retries=0,
        )

    async def complete(self, request: LLMRequest) -> LLMResponse:
        del request
        raise ProviderDisabledError(f"LLM provider is disabled: {self.reason}")

    def __repr__(self) -> str:
        return f"DisabledProvider(reason={self.reason!r})"


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        default_model: str,
        provider_name: str = "openai",
        extra_headers: Mapping[str, str] | None = None,
        model_overrides: Mapping[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        if not base_url.startswith(("https://", "http://")):
            raise ValueError("base_url must be an HTTP(S) URL")
        self.name = provider_name
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._extra_headers = dict(extra_headers or {})
        super().__init__(
            model_router=TaskModelRouter(default_model, model_overrides or {}),
            client=client,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )

    async def complete(self, request: LLMRequest) -> LLMResponse:
        model = self.model_router.resolve(request)
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": message.role.value, "content": message.content}
                for message in request.messages
            ],
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.response_format is not None:
            response_format = request.response_format
            if response_format.type == "json_schema":
                payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": response_format.name,
                        "strict": response_format.strict,
                        "schema": dict(response_format.schema or {}),
                    },
                }
            else:
                payload["response_format"] = {"type": "json_object"}

        response = await self._post_json(
            f"{self._base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                **self._extra_headers,
            },
            payload=payload,
        )
        body = self._response_json(response)
        try:
            choice = body["choices"][0]
            content = _join_text_blocks(choice["message"]["content"])
        except (KeyError, IndexError, TypeError):
            raise ProviderResponseError(f"{self.name} returned no assistant message") from None
        if not content:
            raise ProviderResponseError(f"{self.name} returned an empty assistant message")

        usage_body = body.get("usage", {})
        usage_body = usage_body if isinstance(usage_body, dict) else {}
        input_tokens = _integer(usage_body.get("prompt_tokens"))
        output_tokens = _integer(usage_body.get("completion_tokens"))
        prompt_details = usage_body.get("prompt_tokens_details") or {}
        prompt_details = prompt_details if isinstance(prompt_details, dict) else {}
        usage = Usage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=_integer(usage_body.get("total_tokens")) or input_tokens + output_tokens,
            cache_read_tokens=_integer(prompt_details.get("cached_tokens")),
        )
        return LLMResponse(
            message=Message(MessageRole.ASSISTANT, content),
            usage=usage,
            model=body.get("model") if isinstance(body.get("model"), str) else model,
            provider=self.name,
            finish_reason=choice.get("finish_reason") if isinstance(choice, dict) else None,
            request_id=body.get("id") if isinstance(body.get("id"), str) else None,
        )

    def __repr__(self) -> str:
        return (
            f"OpenAICompatibleProvider(provider_name={self.name!r}, "
            f"base_url={self._base_url!r})"
        )


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        default_model: str,
        api_version: str = "2023-06-01",
        model_overrides: Mapping[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._api_version = api_version
        super().__init__(
            model_router=TaskModelRouter(default_model, model_overrides or {}),
            client=client,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )

    async def complete(self, request: LLMRequest) -> LLMResponse:
        model = self.model_router.resolve(request)
        system_parts = [
            message.content for message in request.messages if message.role is MessageRole.SYSTEM
        ]
        messages = [
            {"role": message.role.value, "content": message.content}
            for message in request.messages
            if message.role is not MessageRole.SYSTEM
        ]
        if not messages:
            raise ProviderRequestError("Anthropic requires at least one user or assistant message")

        if request.response_format is not None:
            instruction = "Return only valid JSON without Markdown code fences."
            if request.response_format.schema is not None:
                instruction += (
                    " The JSON must conform to this schema: "
                    + json.dumps(request.response_format.schema, separators=(",", ":"))
                )
            system_parts.append(instruction)

        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": request.max_tokens or 1024,
            "messages": messages,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        if request.temperature is not None:
            payload["temperature"] = request.temperature

        response = await self._post_json(
            f"{self._base_url}/v1/messages",
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": self._api_version,
            },
            payload=payload,
        )
        body = self._response_json(response)
        content = _join_text_blocks(body.get("content"))
        if not content:
            raise ProviderResponseError("anthropic returned an empty assistant message")

        usage_body = body.get("usage", {})
        usage_body = usage_body if isinstance(usage_body, dict) else {}
        input_tokens = _integer(usage_body.get("input_tokens"))
        output_tokens = _integer(usage_body.get("output_tokens"))
        return LLMResponse(
            message=Message(MessageRole.ASSISTANT, content),
            usage=Usage(
                input_tokens,
                output_tokens,
                input_tokens + output_tokens,
                cache_read_tokens=_integer(usage_body.get("cache_read_input_tokens")),
                cache_write_tokens=_integer(usage_body.get("cache_creation_input_tokens")),
            ),
            model=body.get("model") if isinstance(body.get("model"), str) else model,
            provider=self.name,
            finish_reason=body.get("stop_reason") if isinstance(body.get("stop_reason"), str) else None,
            request_id=body.get("id") if isinstance(body.get("id"), str) else None,
        )

    def __repr__(self) -> str:
        return f"AnthropicProvider(base_url={self._base_url!r})"


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        default_model: str,
        model_overrides: Mapping[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        super().__init__(
            model_router=TaskModelRouter(default_model, model_overrides or {}),
            client=client,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )

    async def complete(self, request: LLMRequest) -> LLMResponse:
        model = self.model_router.resolve(request)
        system_parts = [
            message.content for message in request.messages if message.role is MessageRole.SYSTEM
        ]
        contents = [
            {
                "role": "model" if message.role is MessageRole.ASSISTANT else "user",
                "parts": [{"text": message.content}],
            }
            for message in request.messages
            if message.role is not MessageRole.SYSTEM
        ]
        if not contents:
            raise ProviderRequestError("Gemini requires at least one user or assistant message")

        payload: dict[str, Any] = {"contents": contents}
        if system_parts:
            payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}

        generation_config: dict[str, Any] = {}
        if request.temperature is not None:
            generation_config["temperature"] = request.temperature
        if request.max_tokens is not None:
            generation_config["maxOutputTokens"] = request.max_tokens
        if request.response_format is not None:
            generation_config["responseMimeType"] = "application/json"
            if request.response_format.schema is not None:
                generation_config["responseSchema"] = dict(request.response_format.schema)
        if generation_config:
            payload["generationConfig"] = generation_config

        model_path = model[7:] if model.startswith("models/") else model
        response = await self._post_json(
            f"{self._base_url}/models/{quote(model_path, safe='')}:generateContent",
            headers={"x-goog-api-key": self._api_key},
            payload=payload,
        )
        body = self._response_json(response)
        try:
            candidate = body["candidates"][0]
            content = _join_text_blocks(candidate["content"]["parts"])
        except (KeyError, IndexError, TypeError):
            raise ProviderResponseError("gemini returned no candidate content") from None
        if not content:
            raise ProviderResponseError("gemini returned an empty assistant message")

        usage_body = body.get("usageMetadata", {})
        usage_body = usage_body if isinstance(usage_body, dict) else {}
        input_tokens = _integer(usage_body.get("promptTokenCount"))
        output_tokens = _integer(usage_body.get("candidatesTokenCount"))
        return LLMResponse(
            message=Message(MessageRole.ASSISTANT, content),
            usage=Usage(
                input_tokens,
                output_tokens,
                _integer(usage_body.get("totalTokenCount")) or input_tokens + output_tokens,
                cache_read_tokens=_integer(usage_body.get("cachedContentTokenCount")),
            ),
            model=model,
            provider=self.name,
            finish_reason=(
                candidate.get("finishReason") if isinstance(candidate, dict) else None
            ),
            request_id=(
                response.headers.get("x-request-id")
                or response.headers.get("x-goog-request-id")
            ),
        )

    def __repr__(self) -> str:
        return f"GeminiProvider(base_url={self._base_url!r})"
