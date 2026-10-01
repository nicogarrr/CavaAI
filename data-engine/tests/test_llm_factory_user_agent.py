"""opencode.ai (Cloudflare) devuelve 403 / error 1010 con el User-Agent por defecto de Python."""

from types import SimpleNamespace

from app.llm import factory


def test_opencode_provider_sends_explicit_user_agent():
    settings = SimpleNamespace(
        llm_enabled=True,
        llm_provider="opencode-go",
        opencode_go_api_key="test-key-123456",
        opencode_go_base_url="https://opencode.ai/zen/v1",
        opencode_go_model="space-bunny-free",
        opencode_go_session="sess",
        llm_model_overrides={},
        opencode_go_fallback_model="muse-spark-1.3-contributor-free",
        opencode_go_reasoning_effort="",
        opencode_go_reasoning_effort_models="",
        llm_timeout_seconds=5,
        llm_max_retries=0,
        llm_max_output_tokens=1000,
    )
    provider = factory.create_llm_provider(settings)
    headers = provider._extra_headers
    assert headers["User-Agent"] == factory.OPENCODE_USER_AGENT
    assert not headers["User-Agent"].lower().startswith("python")
