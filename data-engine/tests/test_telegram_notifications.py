from datetime import UTC, datetime
from types import SimpleNamespace

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

    result = notification_service.NotificationService().dispatch(
        _FakeDB(), _alert(["telegram"])
    )

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

    result = notification_service.NotificationService().dispatch(
        _FakeDB(), _alert(["telegram"])
    )

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
