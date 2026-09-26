from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest

from app.services import notification_service
from app.services.public_fetch import validate_public_url


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None


class _FakeClient:
    calls: list[tuple[str, dict]] = []

    def __init__(self, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def post(self, url: str, json: dict):
        self.calls.append((url, json))
        return _FakeResponse()


class _FakeDB:
    def commit(self) -> None:
        return None

    def refresh(self, _alert) -> None:
        return None



def _service_with_stubbed_outbox():
    """NotificationService con el outbox (alert_deliveries) stubado.

    Estos tests cubren el canal Telegram (texto, config, 429); la capa de
    claim atomico tiene sus propios tests con SQLite real en
    test_notification_service.py.
    """
    svc = notification_service.NotificationService()
    svc._ensure_delivery_row = lambda db, alert, channel: None
    svc._claim_delivery = lambda db, alert, channel: True
    svc._finish_delivery = lambda db, alert, channel, status, error: None
    return svc

def _alert(channels: list[str]):
    return SimpleNamespace(
        id=7,
        tenant_id=3,
        company_id=11,
        severity="high",
        alert_type="news",
        title="Material company news",
        message="A material event was detected.",
        created_at=datetime.now(UTC),
        channels=channels,
        metadata_={},
    )


def test_telegram_notification_uses_configured_channel_without_leaking_token(monkeypatch):
    _FakeClient.calls.clear()
    monkeypatch.setattr(notification_service.httpx, "Client", _FakeClient)
    monkeypatch.setattr(
        notification_service,
        "get_settings",
        lambda: SimpleNamespace(
            telegram_enabled=True,
            telegram_bot_token="rotated-test-token",
            telegram_chat_id="12345",
            telegram_api_base_url="https://api.telegram.org",
            telegram_timeout_seconds=10,
        ),
    )

    result = _service_with_stubbed_outbox().dispatch(_FakeDB(), _alert(["telegram"]))

    assert result["telegram"]["status"] == "delivered"
    url, body = _FakeClient.calls[0]
    assert url.endswith("/sendMessage")
    assert body["chat_id"] == "12345"
    assert "Material company news" in body["text"]
    assert "rotated-test-token" not in body["text"]


def test_telegram_notification_is_silent_when_not_configured(monkeypatch):
    monkeypatch.setattr(
        notification_service,
        "get_settings",
        lambda: SimpleNamespace(
            telegram_enabled=False,
            telegram_bot_token=None,
            telegram_chat_id=None,
            telegram_api_base_url="https://api.telegram.org",
            telegram_timeout_seconds=10,
        ),
    )

    result = _service_with_stubbed_outbox().dispatch(_FakeDB(), _alert(["telegram"]))

    assert result["telegram"]["status"] == "not_configured"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/internal",
        "http://localhost/internal",
        "http://169.254.169.254/latest/meta-data",
        "https://user:password@example.com/private",
    ],
)
def test_public_fetch_rejects_private_or_credential_urls(url):
    with pytest.raises(ValueError):
        validate_public_url(url)


class _RateLimitedClient:
    """Telegram devuelve 429: sin reintento en el fuente, un solo intento."""

    attempts = 0

    def __init__(self, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def post(self, url: str, json: dict):
        type(self).attempts += 1
        request = httpx.Request("POST", url, json=json)
        response = httpx.Response(429, request=request)
        raise httpx.HTTPStatusError(
            "429 Too Many Requests", request=request, response=response
        )


def test_telegram_429_fails_honestly_without_retry_storm(monkeypatch):
    """429 → 'throttled' honesto: el servicio no reintenta en caliente (sin
    backoff en el fuente; la fila enfria y solo vuelve via reconciliador por
    claim expirado) y persiste solo la clase de error, nunca el token ni el
    body."""
    _RateLimitedClient.attempts = 0
    monkeypatch.setattr(notification_service.httpx, "Client", _RateLimitedClient)
    monkeypatch.setattr(
        notification_service,
        "get_settings",
        lambda: SimpleNamespace(
            telegram_enabled=True,
            telegram_bot_token="rotated-test-token",
            telegram_chat_id="12345",
            telegram_api_base_url="https://api.telegram.org",
            telegram_timeout_seconds=10,
        ),
    )

    result = _service_with_stubbed_outbox().dispatch(_FakeDB(), _alert(["telegram"]))

    delivery = result["telegram"]
    assert delivery["status"] == "throttled"
    assert delivery["error"] == "HTTPStatusError"
    assert _RateLimitedClient.attempts == 1
    assert "rotated-test-token" not in str(result)
