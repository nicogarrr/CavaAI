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
# Keep TestClient lifespans quiet: the worker scheduler must not start in tests.
os.environ["WORKERS_ENABLED"] = "false"
# Hermetic tests: never inherit the local Postgres stack. Environment
# variables take precedence over the .env file in pydantic-settings, so this
# forces a disposable SQLite file for every test process.
os.environ["DATABASE_URL"] = "sqlite:///./cavaai_test.db"

# Importing main no debe filtrar secretos locales al proceso de test. La API
# legacy (routers/) fue retirada, pero los módulos de servicio (modules/) que
# quedan pueden llamar load_dotenv() en import time. Tests must stay hermetic:
# Settings(_env_file=None) must observe no secrets.
_TEST_ISOLATED_ENV_VARS = (
    "RESEARCH_AUTH_SECRET",
    "DOCUMENT_STORAGE_BACKEND",
    "FMP_API_KEY",
    "FINNHUB_API_KEY",
    "FRED_API_KEY",
    "OPENCODE_GO_API_KEY",
    "TELEGRAM_ENABLED",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "TELEGRAM_API_BASE_URL",
    "TELEGRAM_TIMEOUT_SECONDS",
    "TELEGRAM_APPROVAL_ENABLED",
    "TELEGRAM_APPROVAL_STATE_PATH",
    "TELEGRAM_APPROVAL_POLL_INTERVAL_SECONDS",
    "INSIDER_ALERTS_ENABLED",
    "ALERT_EMAIL_WEBHOOK_URL",
    "ALERT_PUSH_WEBHOOK_URL",
)

# Pydantic Settings still reads .env when the environment variable is absent.
# Explicit safe values therefore win over a developer's local dotenv file.
_TEST_ISOLATED_ENV_DEFAULTS = {
    "TELEGRAM_ENABLED": "false",
    "TELEGRAM_BOT_TOKEN": "",
    "TELEGRAM_CHAT_ID": "",
    "TELEGRAM_API_BASE_URL": "https://api.telegram.org",
    "TELEGRAM_TIMEOUT_SECONDS": "10",
    "TELEGRAM_APPROVAL_ENABLED": "false",
    "TELEGRAM_APPROVAL_STATE_PATH": "./storage/test-telegram-approval-offset",
    "TELEGRAM_APPROVAL_POLL_INTERVAL_SECONDS": "15",
    "INSIDER_ALERTS_ENABLED": "false",
    "ALERT_EMAIL_WEBHOOK_URL": "",
    "ALERT_PUSH_WEBHOOK_URL": "",
}
os.environ.update(_TEST_ISOLATED_ENV_DEFAULTS)


@pytest.fixture(autouse=True)
def isolate_local_dotenv():
    """Remove local delivery config from every test, regardless of import order."""
    saved = {key: os.environ.pop(key) for key in _TEST_ISOLATED_ENV_VARS if key in os.environ}
    os.environ.update(_TEST_ISOLATED_ENV_DEFAULTS)
    try:
        yield
    finally:
        for key in _TEST_ISOLATED_ENV_VARS:
            os.environ.pop(key, None)
        os.environ.update(saved)


@pytest.fixture(autouse=True)
def reset_settings_cache():
    """Clear cached settings after isolation, not just before the test starts."""
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()
