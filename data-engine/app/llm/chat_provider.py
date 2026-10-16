"""Opt-in independent free fallback, scoped to chat, not background LLM jobs."""
from __future__ import annotations

import asyncio
import re
import unicodedata
from collections.abc import Callable
from dataclasses import replace

import httpx

from app.core.config import Settings, get_settings
from app.llm.adapters import OpenAICompatibleProvider
from app.llm.base import LLMProvider
from app.llm.cascade import _FALL_THROUGH, CascadeModelRouter
from app.llm.contracts import LLMRequest, LLMResponse, Message
from app.llm.errors import ProviderRequestError, ProviderResponseError, ProviderTransportError
from app.llm.factory import create_llm_provider
from app.llm.model_aliases import VERIFIED_FREE_MODELS

GROQ_MODEL = "openai/gpt-oss-120b"


def educational_output(text: str) -> bool:
    """Best-effort lexical rejection, NOT a semantic guarantee against advice."""
    value = "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))
    pattern = r"\b(?:recom\w*|aconsej\w*|compr\w*|vend\w*|vender|adquir\w*|adquiera\w*|liquid\w*|invert\w*|asign\w*|buy\w*|sell\w*|allocat\w*|should|deberia\w*)\b"
    return bool(text.strip()) and re.search(pattern, value) is None


class _LanguageRejected(ProviderResponseError):
    def __init__(self, response):
        super().__init__("Candidate language rejected")
        self.response = response


class ChatFallbackProvider(LLMProvider):
    name = "chat-independent-fallback"

    def __init__(self, primary: LLMProvider, backup: LLMProvider, *, total: float = 45, delay: float = 25, validator: Callable[[LLMResponse], None] | None = None, on_response: Callable[[LLMResponse], None] | None = None):
        self.validator = validator
        self.on_response = on_response
        self.primary = primary
        self.backup = backup
        self.total = total
        self.delay = min(delay, total * 2 / 3)
        self.supported_capabilities = primary.supported_capabilities & backup.supported_capabilities
        # Honest composite route, never masquerades as the primary's free model.
        super().__init__(model_router=CascadeModelRouter((primary, backup)), max_retries=0)

    def with_candidate_validator(self, validator, on_response=None):
        # Per-call clone: concurrent requests never share validation context.
        return ChatFallbackProvider(self.primary, self.backup, total=self.total,
                                    delay=self.delay, validator=validator, on_response=on_response)

    async def _candidate(self, provider, request, *, backup=False):
        response = await provider.complete(request)
        if self.on_response is not None:
            self.on_response(response)
        if self.validator is not None and not backup:
            from app.services.llm_output_guard import inspect_response_text
            if inspect_response_text(response.text):
                raise _LanguageRejected(response)
        try:
            if response.degraded or response.finish_reason == "length":
                raise ValueError("truncated or degraded")
            if backup and not educational_output(response.text):
                raise ValueError("educational boundary")
            if self.validator is not None:
                self.validator(response)
        except Exception as exc:
            raise ProviderResponseError(f"Candidate rejected: {exc}") from exc
        return response

    async def complete(self, request: LLMRequest) -> LLMResponse:
        # Chat synthesis only. Other uses retain their own provider/cost gates.
        if request.task not in {"chat", "main_financial_analysis"} or request.tools:
            return await self.primary.complete(request)
        if self.primary.name == "opencode-go" and self.primary.model_router.resolve(request) not in VERIFIED_FREE_MODELS:
            raise ProviderRequestError("Chat fallback refuses a primary not verified free")
        try:
            return await asyncio.wait_for(self._race(request), timeout=self.total)
        except TimeoutError:
            raise ProviderTransportError(self.name, "timeout", 1) from None

    async def _race(self, request: LLMRequest) -> LLMResponse:
        primary = asyncio.create_task(self._candidate(self.primary, request))
        tasks = [primary]
        rejected_primary = None
        try:
            done, _ = await asyncio.wait({primary}, timeout=self.delay)
            if done:
                try:
                    response = primary.result()
                    if response.degraded or response.finish_reason == "length":
                        raise ProviderResponseError("chat response was degraded")
                    return response
                except _FALL_THROUGH as exc:
                    if isinstance(exc, _LanguageRejected):
                        rejected_primary = exc.response
            # Pin backup explicitly. Never send DeepSeek aliases or effort=max.
            backup = asyncio.create_task(self._candidate(self.backup, replace(
                request, model=GROQ_MODEL,
                messages=(*request.messages, Message("system", "Limita la respuesta a explicación y análisis factual educativo. No des asesoramiento financiero personalizado ni recomendaciones de compra, venta o asignación. Si te lo piden, explica ese límite y ofrece datos y riesgos verificables sin aconsejar una decisión.")),
            ), backup=True))
            tasks.append(backup)
            pending = {backup} | ({primary} if not done else set())
            last = None
            while pending:
                done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for task in tasks:  # prefer a valid primary if both finish together
                    if task not in done:
                        continue
                    try:
                        response = task.result()
                        if response.degraded or response.finish_reason == "length":
                            raise ProviderResponseError("chat response was truncated")
                        if task is backup and not educational_output(response.text):
                            raise ProviderResponseError("Groq output rejected by educational boundary")
                        return response
                    except _FALL_THROUGH as exc:
                        last = exc
                        if task is primary and isinstance(exc, _LanguageRejected):
                            rejected_primary = exc.response
            # Only after all candidates fail, hand the primary's language
            # rejection to complete_guarded so its RETRY_HINT can recover.
            # It never wins a race or cancels an eligible valid candidate.
            if rejected_primary is not None:
                return rejected_primary
            if last is not None:
                raise last
            raise ProviderResponseError("chat providers returned no usable response")
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


def create_chat_llm_provider(settings: Settings | None = None, *, client: httpx.AsyncClient | None = None) -> LLMProvider:
    settings = settings or get_settings()
    primary = create_llm_provider(settings, client=client)
    if not settings.groq_chat_fallback_enabled or primary.name == "disabled":
        return primary
    if primary.name != "opencode-go":
        raise ValueError("Groq chat fallback requires the verified OpenCode primary")
    if not (settings.groq_api_key and settings.groq_free_plan_confirmed and settings.groq_zdr_confirmed):
        raise ValueError("Groq chat requires a verified free plan, ZDR and API key")
    backup = OpenAICompatibleProvider(
        api_key=settings.groq_api_key,
        base_url="https://api.groq.com/openai/v1",
        default_model=GROQ_MODEL,
        provider_name="groq",
        extra_headers={"User-Agent": "cavaai/1.0"},
        reasoning_effort="low",
        timeout_seconds=12,
        total_timeout_seconds=15,
        max_retries=0,
        max_output_tokens=2400,
        client=client,
    )
    return ChatFallbackProvider(primary, backup, total=settings.llm_total_timeout_seconds)
