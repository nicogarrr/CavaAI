from app.core.config import Settings
from app.llm.factory import create_llm_provider


def test_defaults_use_go_endpoint_with_free_longcat() -> None:
    settings = Settings(_env_file=None, opencode_go_api_key="k")
    assert settings.opencode_go_base_url == "https://opencode.ai/zen/go/v1"
    assert settings.opencode_go_model == "longcat-2.5-preview-free"


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
