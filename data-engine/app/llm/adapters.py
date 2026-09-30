from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from app.llm.base import LLMProvider
from app.llm.contracts import LLMRequest, LLMResponse, Message, MessageRole, Usage
from app.llm.errors import ProviderDisabledError, ProviderResponseError
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
        fallback_model: str | None = None,
        reasoning_effort: str | None = None,
        reasoning_effort_models: frozenset[str] | set[str] | None = None,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        max_output_tokens: int = 16_000,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        if not base_url.startswith(("https://", "http://")):
            raise ValueError("base_url must be an HTTP(S) URL")
        if max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")
        self.name = provider_name
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._max_output_tokens = max_output_tokens
        self._extra_headers = dict(extra_headers or {})
        # Cadena de fallback: si el modelo resuelto falla en la capa LLM, se
        # reintenta una vez con este modelo (p.ej. el primario deja de
        # existir en el catalogo del proveedor). None = sin fallback.
        self._fallback_model = (fallback_model or "").strip() or None
        # Nivel de razonamiento (sobre OpenAI-compatible: campo
        # `reasoning_effort`). Solo se envia a los modelos de
        # reasoning_effort_models (None = a todos); un modelo que no
        # admita el nivel configurado (p.ej. el fallback con effort=max)
        # no debe recibirlo.
        self._reasoning_effort = (reasoning_effort or "").strip() or None
        self._reasoning_effort_models = (
            frozenset(
                model.strip() for model in reasoning_effort_models if model.strip()
            )
            if reasoning_effort_models is not None
            else None
        )
        super().__init__(
            model_router=TaskModelRouter(default_model, model_overrides or {}, provider_name),
            client=client,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )

    async def complete(self, request: LLMRequest) -> LLMResponse:
        model = self.model_router.resolve(request)
        try:
            return await self._complete_traced(request, model)
        except Exception as primary_exc:
            fallback = self._fallback_model
            if not fallback or fallback == model:
                raise
            # El modelo resuelto fallo tras sus reintentos: una unica
            # oportunidad con el modelo de respaldo (con sus propios
            # reintentos). La traza del respaldo registra de que modelo y
            # de que clase de error se viene.
            return await self._complete_traced(
                request,
                fallback,
                extra_metadata={
                    "fallback_from": model,
                    "primary_error": type(primary_exc).__name__,
                },
            )

    async def _complete_traced(
        self,
        request: LLMRequest,
        model: str,
        extra_metadata: Mapping[str, str] | None = None,
    ) -> LLMResponse:
        # Stage 3: generation span sobre la traza activa (si la hay). Solo
        # metadatos y contadores; prompts y completaciones jamas salen.
        import time as _time

        from app.services import tracing as _tracing

        _started = _time.monotonic()
        try:
            response = await self._complete(request, model)
        except Exception as exc:
            _tracing.trace_generation(
                name=f"llm.{request.task or 'complete'}",
                model=model,
                metadata={
                    "provider": self.name,
                    "task": request.task,
                    "route": model,
                    "duration_ms": int((_time.monotonic() - _started) * 1000),
                    **dict(extra_metadata or {}),
                    **dict(request.metadata or {}),
                },
                error_class=type(exc).__name__,
            )
            raise
        _tracing.trace_generation(
            name=f"llm.{request.task or 'complete'}",
            model=response.model,
            metadata={
                "provider": self.name,
                "task": request.task,
                "route": model,
                "duration_ms": int((_time.monotonic() - _started) * 1000),
                **dict(extra_metadata or {}),
                **dict(request.metadata or {}),
            },
            usage={
                "input": response.usage.input_tokens,
                "output": response.usage.output_tokens,
                "total": response.usage.total_tokens,
                "cache_read": response.usage.cache_read_tokens,
            },
        )
        return response

    async def _complete(self, request: LLMRequest, model: str) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": message.role.value, "content": message.content}
                for message in request.messages
            ],
        }
        if self._reasoning_effort and (
            self._reasoning_effort_models is None
            or model in self._reasoning_effort_models
        ):
            payload["reasoning_effort"] = self._reasoning_effort
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = min(
                request.max_tokens,
                self._max_output_tokens,
            )
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

        usage_body = body.get("usage")
        if not isinstance(usage_body, dict):
            raise ProviderResponseError(f"{self.name} returned missing token usage")
        raw_input_tokens = usage_body.get("prompt_tokens")
        raw_output_tokens = usage_body.get("completion_tokens")
        if not isinstance(raw_input_tokens, int) or raw_input_tokens < 0:
            raise ProviderResponseError(f"{self.name} returned invalid prompt token usage")
        if not isinstance(raw_output_tokens, int) or raw_output_tokens < 0:
            raise ProviderResponseError(f"{self.name} returned invalid completion token usage")
        input_tokens = raw_input_tokens
        output_tokens = raw_output_tokens
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
