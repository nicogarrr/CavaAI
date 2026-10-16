"""Opt-in independent free fallback, scoped to chat, not background LLM jobs."""
from __future__ import annotations

import asyncio
import json

import httpx

from app.core.config import Settings, get_settings
from app.llm.adapters import OpenAICompatibleProvider
from app.llm.base import LLMProvider
from app.llm.cascade import _FALL_THROUGH, CascadeModelRouter
from app.llm.contracts import LLMRequest, LLMResponse, Message
from app.llm.errors import ProviderRequestError, ProviderResponseError, ProviderTransportError
from app.llm.factory import create_llm_provider
from app.llm.general_concepts import canonical_concept, educational_output
from app.llm.model_aliases import VERIFIED_FREE_MODELS

GROQ_MODEL = "openai/gpt-oss-120b"


class ChatFallbackProvider(LLMProvider):
    name = "chat-independent-fallback"

    def __init__(self, primary: LLMProvider, backup: LLMProvider, *, total: float = 45, delay: float = 25):
        self.primary = primary
        self.backup = backup
        self.total = total
        self.delay = min(delay, total * 2 / 3)
        self.supported_capabilities = primary.supported_capabilities & backup.supported_capabilities
        # Honest composite route, never masquerades as the primary's free model.
        super().__init__(model_router=CascadeModelRouter((primary, backup)), max_retries=0)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        # Chat synthesis only. Other uses retain their own provider/cost gates.
        if request.task != "chat" or request.tools or not self._public_concept(request):
            return await self.primary.complete(request)
        if self.primary.name == "opencode-go" and self.primary.model_router.resolve(request) not in VERIFIED_FREE_MODELS:
            raise ProviderRequestError("Chat fallback refuses a primary not verified free")
        try:
            return await asyncio.wait_for(self._race(request), timeout=self.total)
        except TimeoutError:
            raise ProviderTransportError(self.name, "timeout", 1) from None

    @staticmethod
    def _public_concept(request: LLMRequest) -> str | None:
        if request.metadata.get("public_general_concept") is not True:
            return None
        users = [m for m in request.messages if m.role == "user"]
        if len(users) != 1:
            return None
        try:
            payload = json.loads(users[0].content)
        except (ValueError, TypeError):
            return None
        if not isinstance(payload, dict) or payload.get("scope") != "concept":
            return None
        question = payload.get("question")
        return canonical_concept(question) if isinstance(question, str) else None

    async def _race(self, request: LLMRequest) -> LLMResponse:
        primary = asyncio.create_task(self.primary.complete(request))
        tasks = [primary]
        try:
            done, _ = await asyncio.wait({primary}, timeout=self.delay)
            if done:
                try:
                    response = primary.result()
                    if response.degraded or response.finish_reason == "length":
                        raise ProviderResponseError("chat response was degraded")
                    return response
                except _FALL_THROUGH:
                    pass
            # Pin backup explicitly. Never send DeepSeek aliases or effort=max.
            backup = asyncio.create_task(self.backup.complete(LLMRequest(
                task="chat", model=GROQ_MODEL, temperature=0.3, max_tokens=600,
                messages=(
                    Message("system", "Explica conceptos financieros generales en español, solo con fines educativos. No des asesoramiento financiero personalizado ni recomendaciones de compra, venta o asignación. No uses lenguaje personalizado ni enlaces. Máximo 100 palabras. Texto plano, sin Markdown, LaTeX, corchetes ni términos en inglés. Solo definición, fórmula y limitaciones generales. No menciones oportunidades ni decisiones de compra, venta o inversión."),
                    Message("user", f"Define el concepto general: {self._public_concept(request)}."),
                ), metadata={}, response_format=None, cache=None, tools=(), tool_choice=None,
            )))
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
