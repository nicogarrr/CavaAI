
"""Daily-digest outbound alert: routing, idempotency and honest copy."""
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.routes.alerts import (
    TelegramSubscriptionIn,
    list_telegram_subscriptions,
    set_telegram_subscription,
)
from app.models import PortfolioMoveDigest, ResearchAlert, Tenant
from app.models.entities import Base
from app.services.daily_digest_alerts import VERSION, emit_digest_alert
from app.services.outbound_alerts import EVENT_TYPES, dispatch_pending, event_type, subscription_for

AS_OF = date(2026, 10, 9)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Tenant(id=1, external_id="owner"))
        db.commit()
        db.info.update(tenant_id=1, user_id="owner")
        yield db
    engine.dispose()


def make_digest(db, items=None, coverage="complete"):
    row = PortfolioMoveDigest(
        tenant_id=1, digest_date=AS_OF, version="test-v1", input_hash="abc123",
        items=items if items is not None else [
            {"ticker": "ASTS", "status": "disponible", "price_change_pct": 2.5},
            {"ticker": "NBIS", "status": "sin datos"},
        ],
        coverage=coverage, generated_at=datetime(2026, 10, 10, 5, 15, tzinfo=UTC),
    )
    db.add(row)
    db.commit()
    return row


def opt_in(db):
    from app.models.entities import TelegramChatBinding
    if db.scalar(select(TelegramChatBinding)) is None:
        db.add(TelegramChatBinding(user_id="owner", chat_id="12345"))
        db.commit()
    return set_telegram_subscription("daily_digest", TelegramSubscriptionIn(enabled=True, chat_id="12345"), db)


def test_event_type_routes_daily_digest(db):
    digest = make_digest(db)
    alert = emit_digest_alert(db, digest, AS_OF)
    assert alert is not None
    assert event_type(db, alert) == "daily_digest"
    assert "daily_digest" in EVENT_TYPES


def test_subscription_api_accepts_daily_digest(db):
    kinds = [r["event_type"] for r in list_telegram_subscriptions(db)]
    assert "daily_digest" in kinds
    out = opt_in(db)
    assert out["enabled"] is True
    assert out["event_type"] == "daily_digest"


def test_emit_is_idempotent_per_tenant_day(db):
    digest = make_digest(db)
    first = emit_digest_alert(db, digest, AS_OF)
    second = emit_digest_alert(db, digest, AS_OF)
    assert first is not None and second is None
    rows = db.scalars(select(ResearchAlert).where(ResearchAlert.alert_type == "daily_digest")).all()
    assert len(rows) == 1


def test_emit_requires_tenant(db):
    digest = make_digest(db)
    db.info.pop("tenant_id")
    with pytest.raises(ValueError):
        emit_digest_alert(db, digest, AS_OF)


def test_copy_carries_source_and_date(db):
    digest = make_digest(db)
    alert = emit_digest_alert(db, digest, AS_OF)
    assert AS_OF.isoformat() in alert.message
    assert "yfinance" in alert.message
    assert "ASTS" in alert.message
    assert "NBIS" not in alert.message  # sin datos no se mezcla con lo cubierto
    assert alert.metadata_["price_source"] == "yfinance"
    assert alert.metadata_["rule_version"] == VERSION


def test_zero_positions_still_emits_honest_copy(db):
    digest = make_digest(db, items=[], coverage="sin_posiciones")
    alert = emit_digest_alert(db, digest, AS_OF)
    assert alert is not None
    assert "No habia posiciones" in alert.message


def test_all_missing_data_is_not_zero(db):
    digest = make_digest(db, items=[{"ticker": "X", "status": "sin datos"}], coverage="partial")
    alert = emit_digest_alert(db, digest, AS_OF)
    assert "sin datos" in alert.message
    assert "0 posiciones con cierre" not in alert.message


def test_subscription_matches_alert_emitted_after_opt_in(db):
    opt_in(db)
    digest = make_digest(db)
    alert = emit_digest_alert(db, digest, AS_OF)
    sub = subscription_for(db, alert)
    assert sub is not None and sub.event_type == "daily_digest"


def test_opt_in_is_not_retroactive(db):
    digest = make_digest(db)
    alert = emit_digest_alert(db, digest, AS_OF)
    opt_in(db)
    assert subscription_for(db, alert) is None


def test_dispatch_skips_when_subscribed_to_other_type(db):
    from app.models.entities import TelegramChatBinding
    db.add(TelegramChatBinding(user_id="owner", chat_id="12345"))
    db.commit()
    set_telegram_subscription("insiders", TelegramSubscriptionIn(enabled=True, chat_id="12345"), db)
    digest = make_digest(db)
    emit_digest_alert(db, digest, AS_OF)
    stats = dispatch_pending(db)
    assert stats["redispatched"] == 0
    assert stats["candidates"] == 0  # no cuela por la suscripcion a insiders


def test_dispatch_no_subscriptions_is_early_return(db):
    digest = make_digest(db)
    emit_digest_alert(db, digest, AS_OF)
    stats = dispatch_pending(db)
    assert stats == {"candidates": 0, "redispatched": 0, "errors": []}
