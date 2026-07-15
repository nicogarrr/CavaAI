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


@pytest.fixture(autouse=True)
def reset_settings_cache():
    """Prevent environment/cache leakage between auth and service-level tests."""
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
