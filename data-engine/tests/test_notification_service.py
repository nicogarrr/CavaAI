"""NotificationService contract tests.

Alert delivery must be honest per channel: in_app always delivers,
unconfigured channels say so explicitly, failures are recorded without
leaking URLs or bodies, and every attempt is persisted on the alert.
"""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, Company, ResearchAlert
from app.services import notification_service
from app.services.notification_service import NotificationService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _alert(db: Session, channels: list[str], metadata: dict | None = None) -> ResearchAlert:
    company = Company(
        ticker="AAPL", name="Apple", exchange="NASDAQ", currency="USD",
        sector="Tech", industry="Tech", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.flush()
    alert = ResearchAlert(
        company_id=company.id, alert_type="price_above", severity="high",
        title="AAPL: price_above > 200", message="AAPL rule matched: observed=210",
        fingerprint="fp-test-1", channels=channels, metadata_=metadata or {},
    )
    db.add(alert)
    db.commit()
    return alert


def test_in_app_delivers_and_unconfigured_channels_say_so(db):
    alert = _alert(db, ["in_app", "email", "push"])
    deliveries = NotificationService().dispatch(db, alert)

    assert deliveries["in_app"]["status"] == "delivered"
    assert deliveries["email"]["status"] == "not_configured"
    assert deliveries["push"]["status"] == "not_configured"
    assert "No webhook configured" in deliveries["email"]["error"]
    # Every attempt persisted on the alert row.
    db.refresh(alert)
    assert set(alert.metadata_["deliveries"]) == {"in_app", "email", "push"}
    for entry in alert.metadata_["deliveries"].values():
        datetime.fromisoformat(entry["attempted_at"])


def test_telegram_not_configured_without_credentials(db):
    alert = _alert(db, ["telegram"])
    deliveries = NotificationService().dispatch(db, alert)
    assert deliveries["telegram"]["status"] == "not_configured"
    assert "TELEGRAM_ENABLED" in deliveries["telegram"]["error"]


def test_configured_telegram_failure_does_not_leak_token_or_url(monkeypatch, db):
    token = "telegram-secret-token"
    endpoint = f"https://api.telegram.org/bot{token}/sendMessage"

    class _FailingClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, url, json):
            raise RuntimeError(f"request to {url} failed for {json}")

    monkeypatch.setattr(notification_service.httpx, "Client", _FailingClient)
    monkeypatch.setattr(
        notification_service,
        "get_settings",
        lambda: SimpleNamespace(
            telegram_enabled=True,
            telegram_bot_token=token,
            telegram_chat_id="12345",
            telegram_api_base_url="https://api.telegram.org",
            telegram_timeout_seconds=10,
        ),
    )

    deliveries = NotificationService().dispatch(db, _alert(db, ["telegram"]))

    assert deliveries["telegram"]["status"] == "failed"
    error = deliveries["telegram"]["error"]
    assert "RuntimeError" in error
    assert token not in error
    assert endpoint not in error


def test_webhook_failure_does_not_persist_url_or_body(monkeypatch, db):
    endpoint = "https://hooks.example/secret?token=private"

    class _FailingClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, url, json):
            raise RuntimeError(f"request {url} failed with {json}")

    monkeypatch.setattr(notification_service.httpx, "Client", _FailingClient)
    monkeypatch.setattr(
        notification_service,
        "get_settings",
        lambda: SimpleNamespace(
            alert_email_webhook_url=endpoint,
            alert_push_webhook_url=endpoint,
        ),
    )

    deliveries = NotificationService().dispatch(db, _alert(db, ["email", "push"]))
    for channel in ("email", "push"):
        assert deliveries[channel]["status"] == "failed"
        assert deliveries[channel]["error"] == "RuntimeError"
        assert endpoint not in deliveries[channel]["error"]


def test_telegram_text_format_and_jev_line():
    payload = {
        "severity": "high", "title": "AAPL price alert", "message": "matched",
        "company_id": 7, "alert_id": 42,
        "jev_urgency": {"label": "urgent", "confidence": 0.9},
    }
    text = NotificationService._telegram_text(payload)
    assert text.startswith("[HIGH] AAPL price alert")
    assert "Alert id: 42" in text
    assert "Jev urgency: urgent (conf 0.90)" in text

    # No Jev metadata: no Jev line (fallback stays silent, never fabricated).
    payload["jev_urgency"] = {}
    assert "Jev urgency" not in NotificationService._telegram_text(payload)
    # Telegram plain-text cap.
    payload["message"] = "x" * 9000
    assert len(NotificationService._telegram_text(payload)) <= 4090
