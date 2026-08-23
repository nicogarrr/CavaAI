"""Explicit test-only environment defaults.

Research authentication is mandatory in the application. Most service tests do
not exercise the HTTP identity bridge, so they opt out here. Dedicated security
tests override the dependency and verify signed, tenant-scoped requests.
"""

from __future__ import annotations

import os

import pytest


os.environ.setdefault("APP_ENV", "test")
os.environ["RESEARCH_AUTH_REQUIRED"] = "false"
# Hermetic tests: never inherit the local Postgres stack. Environment
# variables take precedence over the .env file in pydantic-settings, so this
# forces a disposable SQLite file for every test process.
os.environ["DATABASE_URL"] = "sqlite:///./cavaai_test.db"

# Importing main pulls in legacy market modules that call load_dotenv() at
# import time, which would leak local development secrets (provider API keys,
# storage backends and the research auth secret) into the process environment.
# Tests must stay hermetic: Settings(_env_file=None) must observe no secrets.
_TEST_ISOLATED_ENV_VARS = (
    "RESEARCH_AUTH_SECRET",
    "DOCUMENT_STORAGE_BACKEND",
    "FMP_API_KEY",
    "FINNHUB_API_KEY",
    "FRED_API_KEY",
    "OPENCODE_GO_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
)


@pytest.fixture(autouse=True)
def isolate_local_dotenv():
    """Scrub dotenv-injected secrets for every test, regardless of import order."""
    saved = {key: os.environ.pop(key) for key in _TEST_ISOLATED_ENV_VARS if key in os.environ}
    yield
    os.environ.update(saved)


@pytest.fixture(autouse=True)
def reset_settings_cache():
    """Prevent environment/cache leakage between auth and service-level tests."""
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
