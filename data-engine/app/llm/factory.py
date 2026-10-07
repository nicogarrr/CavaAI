from __future__ import annotations

import httpx

from app.core.config import Settings, get_settings
from app.llm.adapters import DisabledProvider, OpenAICompatibleProvider
from app.llm.base import LLMProvider
from app.llm.response_cache import build_response_cache


def _has_key(value: str | None) -> bool:
    return bool(value and value.strip())


def create_llm_provider(
    settings: Settings | None = None,
    *,
    client: httpx.AsyncClient | None = None,
) -> LLMProvider:
    """Create the single application LLM provider: OpenCode Go."""
    settings = settings or get_settings()
    if not settings.llm_enabled:
        return DisabledProvider("disabled_by_configuration")

    requested = settings.llm_provider.strip().lower()
    if requested in {"auto", "opencode", "opencode_go"}:
        requested = "opencode-go"
    if requested not in {"opencode-go", "disabled"}:
        raise ValueError(
            "CavaAI supports only the OpenCode Go provider; "
            f"received {settings.llm_provider!r}"
        )
    if requested == "disabled":
        return DisabledProvider("disabled_by_configuration")
    if not _has_key(settings.opencode_go_api_key):
        return DisabledProvider("opencode_go_api_key_not_configured")

    return OpenAICompatibleProvider(
        api_key=settings.opencode_go_api_key,
        base_url=settings.opencode_go_base_url,
        default_model=settings.opencode_go_model,
        provider_name="opencode-go",
        extra_headers={
            # OpenCode Go documenta: user agent propio (no el generico de la
            # libreria HTTP) + session id estable. https://opencode.ai/docs/go/
            "User-Agent": "cavaai/1.0",
            "x-opencode-session": settings.opencode_go_session,
        },
        model_overrides=settings.llm_model_overrides,
        fallback_model=settings.opencode_go_fallback_model,
        reasoning_effort=settings.opencode_go_reasoning_effort,
        reasoning_effort_models={
            model.strip()
            for model in settings.opencode_go_reasoning_effort_models.split(",")
            if model.strip()
        },
        response_cache=build_response_cache(settings),
        client=client,
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        total_timeout_seconds=settings.llm_total_timeout_seconds,
        hidden_reasoning_models={
            model.strip()
            for model in settings.llm_hidden_reasoning_models.split(",")
            if model.strip()
        },
        hidden_reasoning_min_tokens=settings.llm_hidden_reasoning_min_tokens,
        max_output_tokens=settings.llm_max_output_tokens,
    )


create_provider = create_llm_provider


def validate_llm_configuration(settings: Settings | None = None) -> None:
    """Validate the single-provider configuration without making a request."""
    provider = create_llm_provider(settings or get_settings())
    if provider.name != "disabled":
        return
