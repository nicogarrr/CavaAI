from app.core.config import Settings
from app.llm.factory import create_llm_provider


def test_defaults_use_zen_endpoint_with_free_space_bunny() -> None:
    # Medido el 2026-10-07: space-bunny-free responde 200 en zen/v1 (~2 s) y da
    # 400 "Model is unavailable" en zen/go/v1; LongCat solo va en go/v1 y tarda
    # 22-28 s gastando el presupuesto en razonamiento. El default sin env debe
    # ser la combinacion que funciona.
    settings = Settings(_env_file=None, opencode_go_api_key="k")
    assert settings.opencode_go_base_url == "https://opencode.ai/zen/v1"
    assert settings.opencode_go_model == "space-bunny-free"


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
        llm_model_overrides={"space-bunny-free": "longcat-2.5-preview-free"},
    )
    provider = create_llm_provider(settings)
    for task in ("pdf_summary", "kpi_extraction", "claim_extraction"):
        request = LLMRequest(messages=[Message("user", "x")], task=task)
        assert provider.model_router.resolve(request) == "longcat-2.5-preview-free"


def test_override_also_moves_a_model_pinned_in_code() -> None:
    from app.llm.contracts import LLMRequest, Message
    from app.llm.model_aliases import VERIFIED_FREE_MODELS

    settings = Settings(
        _env_file=None,
        opencode_go_api_key="k",
        llm_model_overrides={"space-bunny-free": "longcat-2.5-preview-free"},
    )
    provider = create_llm_provider(settings)
    request = LLMRequest(messages=[Message("user", "x")], model="space-bunny-free")
    resolved = provider.model_router.resolve(request)
    assert resolved == "longcat-2.5-preview-free"
    assert resolved in VERIFIED_FREE_MODELS
