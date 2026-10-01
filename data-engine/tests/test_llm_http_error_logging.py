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
