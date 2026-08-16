from __future__ import annotations

import httpx

from app.core.config import Settings, get_settings
from app.llm.adapters import DisabledProvider, OpenAICompatibleProvider
from app.llm.base import LLMProvider


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
        model_overrides=settings.llm_model_overrides,
        client=client,
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )


create_provider = create_llm_provider


def validate_llm_configuration(settings: Settings | None = None) -> None:
    """Validate the single-provider configuration without making a request."""
    provider = create_llm_provider(settings or get_settings())
    if provider.name != "disabled":
        return
