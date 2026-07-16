from __future__ import annotations

import httpx

from app.core.config import Settings, get_settings
from app.llm.adapters import (
    AnthropicProvider,
    DisabledProvider,
    GeminiProvider,
    OpenAICompatibleProvider,
)
from app.llm.base import LLMProvider
from app.llm.model_aliases import MODEL_ALIASES


def _has_key(value: str | None) -> bool:
    return bool(value and value.strip())


def create_llm_provider(
    settings: Settings | None = None,
    *,
    client: httpx.AsyncClient | None = None,
) -> LLMProvider:
    settings = settings or get_settings()
    if not settings.llm_enabled:
        return DisabledProvider("disabled_by_configuration")

    requested = settings.llm_provider.strip().lower()
    aliases = {
        "openai-compatible": "openai",
        "openai_compatible": "openai",
        "custom": "openai",
    }
    requested = aliases.get(requested, requested)
    supported = {"auto", "openrouter", "openai", "anthropic", "gemini", "disabled"}
    if requested not in supported:
        raise ValueError(f"Unsupported LLM provider: {requested!r}")
    if requested == "disabled":
        return DisabledProvider("disabled_by_configuration")

    if requested == "auto":
        # Backwards-compatible spelling for the OpenRouter-first policy.  Do
        # not silently move a task onto a provider whose model aliases and
        # capabilities have not been registered.
        requested = "openrouter"

    enabled = getattr(settings, f"{requested}_enabled")
    key = getattr(settings, f"{requested}_api_key")
    if not enabled:
        return DisabledProvider(f"{requested}_disabled_by_configuration")
    if not _has_key(key):
        return DisabledProvider(f"{requested}_api_key_not_configured")

    from app.services.llm_router import ROUTES

    if requested == "openrouter":
        MODEL_ALIASES.validate_active_routes(
            ROUTES.values(),
            provider=requested,
            overrides=settings.llm_model_overrides,
        )
        resolved_overrides = MODEL_ALIASES.translated_overrides(
            provider=requested,
            overrides=settings.llm_model_overrides,
        )
    else:
        missing_tasks = sorted(
            route.task
            for route in ROUTES.values()
            if route.task not in settings.llm_model_overrides
            and route.model not in settings.llm_model_overrides
        )
        if missing_tasks:
            raise ValueError(
                f"Explicit {requested} configuration requires model overrides "
                f"for every active task; missing: {', '.join(missing_tasks)}"
            )
        resolved_overrides = dict(settings.llm_model_overrides)
    common = {
        "client": client,
        "timeout_seconds": settings.llm_timeout_seconds,
        "max_retries": settings.llm_max_retries,
        "model_overrides": resolved_overrides,
    }
    if requested == "openrouter":
        extra_headers = {"X-Title": settings.openrouter_app_name}
        if settings.openrouter_site_url:
            extra_headers["HTTP-Referer"] = settings.openrouter_site_url
        return OpenAICompatibleProvider(
            api_key=key,
            base_url=settings.openrouter_base_url,
            default_model=settings.openrouter_model,
            provider_name="openrouter",
            extra_headers=extra_headers,
            **common,
        )
    if requested == "openai":
        return OpenAICompatibleProvider(
            api_key=key,
            base_url=settings.openai_base_url,
            default_model=settings.openai_model,
            provider_name="openai",
            **common,
        )
    if requested == "anthropic":
        return AnthropicProvider(
            api_key=key,
            base_url=settings.anthropic_base_url,
            default_model=settings.anthropic_model,
            api_version=settings.anthropic_api_version,
            **common,
        )
    return GeminiProvider(
        api_key=key,
        base_url=settings.gemini_base_url,
        default_model=settings.gemini_model,
        **common,
    )


create_provider = create_llm_provider


def validate_llm_configuration(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    provider = create_llm_provider(settings)
    if provider.name != "disabled":
        # Provider construction performs strict route validation and alias
        # translation. Reaching this branch proves the active configuration.
        return
