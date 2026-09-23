"""Sanitized error details for HTTP responses.

Internal exception text must never reach API clients: it can leak stack
context, SQL fragments, credentials or vendor internals. Instead, the client
gets a generic, status-appropriate message plus a short correlation id; the
full exception is logged server-side keyed by that same id so support can
correlate a user report with the server log.
"""

from __future__ import annotations

import logging
import uuid

logger = logging.getLogger("cavaai.request_errors")

_STATUS_DEFAULTS: dict[int, str] = {
    400: "Invalid request",
    401: "Unauthenticated",
    403: "Forbidden",
    404: "Resource not found",
    409: "Conflicting state",
    422: "Invalid request",
    424: "Upstream dependency failed",
    429: "Rate limited by upstream provider",
    500: "Internal server error",
    502: "Upstream error",
    503: "Service unavailable",
}


def safe_detail(exc: Exception, status_code: int) -> str:
    """Log ``exc`` server-side and return a generic client-safe detail.

    The returned message carries only the correlation id — never the raw
    exception text — so callers can replace ``detail=str(exc)``-style raises
    directly.
    """
    ref = uuid.uuid4().hex[:12]
    logger.error(
        "request_error ref=%s status=%s type=%s: %s",
        ref,
        status_code,
        type(exc).__name__,
        exc,
        exc_info=exc,
    )
    base = _STATUS_DEFAULTS.get(status_code, "Request failed")
    return f"{base} (ref: {ref})"
