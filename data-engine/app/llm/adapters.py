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
            model_router=TaskModelRouter(default_model, model_overrides or {}, provider_name),
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
