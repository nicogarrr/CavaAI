"""Sanitized error details for HTTP responses.

Internal exception text must never reach API clients: it can leak stack
context, SQL fragments, credentials or vendor internals. Instead, the client
gets a generic, status-appropriate message plus a short correlation id; the
full exception is logged server-side keyed by that same id so support can
correlate a user report with the server log.
"""

from __future__ import annotations

import logging
import re
import traceback
import uuid

logger = logging.getLogger("cavaai.request_errors")

# Credenciales de proveedor en query string (?token=, ?apikey=, ?api_key=...).
# Los clientes de mercado (Finnhub, FMP, AlphaVantage, TwelveData) las llevan
# ahi, y httpx/fetch meten la URL completa en el texto de sus excepciones, de
# modo que sin esto la key del servidor acaba en el log y a veces en la
# respuesta. Se aplica tambien al log: el log no es un sitio seguro.
_SECRET_QUERY_RE = re.compile(
    r"(?i)\b(token|apikey|api_key|api-key|access_token|secret_key|signature|sig)=([^&\s\"'<>]+)"
)


def redact_secrets(text: str) -> str:
    """Sustituye el valor de los parametros de credencial por REDACTED."""
    return _SECRET_QUERY_RE.sub(r"\1=REDACTED", text)

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
    # El log tampoco es un sitio seguro: el texto de la excepcion y el
    # traceback llevan la URL del proveedor con su key (httpx la incluye en
    # el mensaje de HTTPStatusError). Se loguea el traceback formateado y
    # REDACTED, nunca exc_info=exc en crudo.
    logger.error(
        "request_error ref=%s status=%s type=%s\n%s",
        ref,
        status_code,
        type(exc).__name__,
        redact_secrets("".join(traceback.format_exception(type(exc), exc, exc.__traceback__))),
    )
    base = _STATUS_DEFAULTS.get(status_code, "Request failed")
    return f"{base} (ref: {ref})"
