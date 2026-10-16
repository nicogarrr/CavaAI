from app.core.config import Settings
from app.llm.factory import create_llm_provider


def test_defaults_use_zen_endpoint_with_free_deepseek() -> None:
    # Medido el 2026-10-15/16: el free tier de Zen solo responde desde el
    # cliente OpenCode real (serve enjaulado); por API directa TODOS los free
    # dan 403 FreeTierError. Desde 4a6ebc16 el default sin env es
    # deepseek-v4.1-flash-free (multimodal, tool_call, variants de
    # reasoningEffort) y prod lo sirve via el puente OpenCode.
    settings = Settings(_env_file=None, opencode_go_api_key="k")
    assert settings.opencode_go_base_url == "https://opencode.ai/zen/v1"
    assert settings.opencode_go_model == "deepseek-v4.1-flash-free"


def test_provider_sends_own_user_agent_and_session_header() -> None:
    provider = create_llm_provider(Settings(_env_file=None, opencode_go_api_key="k"))
    headers = provider._extra_headers  # noqa: SLF001
    assert headers["User-Agent"] == "cavaai/1.0"
    assert headers["x-opencode-session"]


def test_one_override_moves_every_extraction_route_to_longcat() -> None:
    from app.llm.contracts import LLMRequest, Message

    settings = Settings(
        _env_file=None,
        opencode_go_api_key="k",
        llm_model_overrides={"deepseek-v4.1-flash-free": "longcat-2.5-preview-free"},
    )
    provider = create_llm_provider(settings)
    for task in ("pdf_summary", "kpi_extraction", "claim_extraction"):
        request = LLMRequest(messages=[Message("user", "x")], task=task)
        assert provider.model_router.resolve(request) == "longcat-2.5-preview-free"


def test_override_also_moves_a_model_pinned_in_code() -> None:
    from app.llm.contracts import LLMRequest, Message
    from app.llm.model_aliases import VERIFIED_FREE_MODELS

    # El override keyed por modelo tambien alcanza al modelo fijado en el
    # request (el guard de pago bloquea en ejecucion si el destino no es
    # gratuito verificado; aqui el destino sigue siendo free).
    settings = Settings(
        _env_file=None,
        opencode_go_api_key="k",
        llm_model_overrides={"deepseek-v4.1-flash-free": "space-bunny-free"},
    )
    provider = create_llm_provider(settings)
    request = LLMRequest(messages=[Message("user", "x")], model="deepseek-v4.1-flash-free")
    resolved = provider.model_router.resolve(request)
    assert resolved == "space-bunny-free"
    assert resolved in VERIFIED_FREE_MODELS
