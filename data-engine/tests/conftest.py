"""Explicit test-only environment defaults.

Research authentication is mandatory in the application. Most service tests do
not exercise the HTTP identity bridge, so they opt out here. Dedicated security
tests override the dependency and verify signed, tenant-scoped requests.
"""

from __future__ import annotations

import os


os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("RESEARCH_AUTH_REQUIRED", "false")
