"""Contract: the production env example documents exactly the Langfuse knobs
the code reads, with the verified EU host and safe defaults."""

from pathlib import Path

from app.core.config import Settings

EXAMPLE = Path(__file__).parents[2] / ".env.production.example"


def test_env_example_documents_all_langfuse_vars():
    text = EXAMPLE.read_text()
    for var in (
        "LANGFUSE_ENABLED",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_HOST",
        "LANGFUSE_SAMPLE_RATE",
    ):
        assert f"{var}=" in text, f"{var} missing from .env.production.example"


def test_env_example_uses_verified_eu_host():
    text = EXAMPLE.read_text()
    assert "LANGFUSE_HOST=https://cloud.langfuse.com" in text
    # eu.cloud is signup/login web only (302 on the API) — never the SDK host
    assert "LANGFUSE_HOST=https://eu.cloud" not in text


def test_safe_defaults_match_config(monkeypatch):
    for var in (
        "LANGFUSE_ENABLED",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_HOST",
        "LANGFUSE_SAMPLE_RATE",
    ):
        monkeypatch.delenv(var, raising=False)
    settings = Settings(_env_file=None)
    assert settings.langfuse_enabled is False          # off by default
    assert settings.langfuse_host == "https://cloud.langfuse.com"
    assert settings.langfuse_sample_rate == 0.1
    assert settings.langfuse_public_key is None        # secrets never defaulted
    assert settings.langfuse_secret_key is None
