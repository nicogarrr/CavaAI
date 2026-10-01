"""Un 4xx/5xx del proveedor deja estado, modelo y cuerpo truncado en el log, sin la key."""

import asyncio
import logging

import httpx
import pytest

from app.llm.adapters import OpenAICompatibleProvider
from app.llm.errors import ProviderHTTPError


def _provider(status: int, body: str) -> OpenAICompatibleProvider:
    transport = httpx.MockTransport(lambda request: httpx.Response(status, text=body))
    return OpenAICompatibleProvider(
        api_key="secret-key-abc",
        base_url="https://example.test/v1",
        default_model="m",
        provider_name="opencode-go",
        client=httpx.AsyncClient(transport=transport),
        max_retries=0,
    )


def test_403_logs_status_model_and_truncated_body_without_key(caplog):
    provider = _provider(403, "error code: 1010 " + "x" * 500)
    headers = {"Authorization": "Bearer secret-key-abc"}
    with caplog.at_level(logging.WARNING, logger="app.llm.base"):
        with pytest.raises(ProviderHTTPError):
            asyncio.run(
                provider._post_json(
                    "https://example.test/v1/chat/completions",
                    headers=headers,
                    payload={"model": "space-bunny-free"},
                )
            )
    text = caplog.text
    assert "HTTP 403" in text
    assert "space-bunny-free" in text
    assert "error code: 1010" in text
    assert "secret-key-abc" not in text
    assert "x" * 300 not in text


def _log_for(body: str, caplog, headers=None) -> str:
    provider = _provider(401, body)
    with caplog.at_level(logging.WARNING, logger="app.llm.base"):
        with pytest.raises(ProviderHTTPError):
            asyncio.run(
                provider._post_json(
                    "https://example.test/v1/chat/completions",
                    headers=headers or {"Authorization": "Bearer secret-key-abc"},
                    payload={"model": "m"},
                )
            )
    return caplog.text


def test_known_provider_key_in_body_is_redacted(caplog):
    text = _log_for("Invalid API key: secret-key-abc", caplog)
    assert "secret-key-abc" not in text
    assert "[REDACTED]" in text


def test_header_secret_echoed_in_body_is_redacted(caplog):
    text = _log_for(
        "bad auth header-secret-9999 rejected",
        caplog,
        headers={"Authorization": "Bearer header-secret-9999"},
    )
    assert "header-secret-9999" not in text


@pytest.mark.parametrize(
    "body,leak",
    [
        ("Authorization: Bearer abc.DEF-123_xyz", "abc.DEF-123_xyz"),
        ("Incorrect API key provided: sk-proj-LEAKLEAK1234", "LEAKLEAK1234"),
        ('{"error":{"api_key":"zzTOPSECRET99"}}', "zzTOPSECRET99"),
        ("x-api-key=OTHERKEY123456", "OTHERKEY123456"),
        ("token: tok_live_9988776655", "tok_live_9988776655"),
    ],
)
def test_common_credential_patterns_are_redacted(caplog, body, leak):
    text = _log_for(body, caplog)
    assert leak not in text


def test_redaction_happens_before_truncation(caplog):
    secret_body = "x" * 190 + " Bearer LONGSECRETTOKEN123456"
    text = _log_for(secret_body, caplog)
    assert "LONGSECRETTOKEN" not in text
    assert "LONGSEC" not in text


def test_non_secret_diagnostic_text_survives(caplog):
    text = _log_for("error code: 1010", caplog)
    assert "error code: 1010" in text


from app.llm.base import redact_secrets  # noqa: E402


def test_known_secret_with_colon_is_fully_redacted_not_fragmented():
    out = redact_secrets("Bearer alpha:betasecret", ["alpha:betasecret"])
    assert "betasecret" not in out
    assert "alpha" not in out


def test_known_secret_with_unicode_is_redacted():
    out = redact_secrets("clave rechazada: llavé-ñandú-ß9", ["llavé-ñandú-ß9"])
    assert "llavé" not in out and "ñandú" not in out


def test_short_known_secret_is_redacted_without_length_gate():
    out = redact_secrets("bad key ab1", ["ab1"])
    assert "ab1" not in out


def test_longer_known_secret_wins_over_its_prefix():
    out = redact_secrets("k=abcd1234 and abcd", ["abcd", "abcd1234"])
    assert "1234" not in out


def test_reflected_key_in_model_field_and_short_key_are_sanitized(caplog):
    provider = OpenAICompatibleProvider(
        api_key="k-9",
        base_url="https://example.test/v1",
        default_model="m",
        provider_name="opencode-go",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(403, text="nope k-9"))
        ),
        max_retries=0,
    )
    with caplog.at_level(logging.WARNING, logger="app.llm.base"):
        with pytest.raises(ProviderHTTPError):
            asyncio.run(
                provider._post_json(
                    "https://example.test/v1/chat/completions",
                    headers={"Authorization": "Bearer k-9"},
                    payload={"model": "model-k-9-x"},
                )
            )
    assert "k-9" not in caplog.text
