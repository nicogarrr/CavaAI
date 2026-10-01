"""F374: each trigger occurrence is its own alert and gets delivered again."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, ResearchAlert
from app.services.alert_rule_service import AlertRuleService
from tests.test_alert_rule_service import _company, _price


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def test_retrigger_after_cooldown_creates_new_alert(db):
    company = _company(db)
    _price(db, company, day=date.today(), close="210")
    service = AlertRuleService()
    rule = service.create(db, company, rule_type="price_above", operator=">", value=200)

    assert service.evaluate(db, rule)["status"] == "triggered"
    # Inside cooldown: no second alert.
    assert service.evaluate(db, rule)["cooldown_active"] is True
    assert db.query(ResearchAlert).count() == 1

    rule.last_triggered_at = datetime.now(UTC) - timedelta(seconds=rule.cooldown_seconds + 5)
    db.commit()
    assert service.evaluate(db, rule)["status"] == "triggered"
    assert db.query(ResearchAlert).count() == 2
    assert rule.trigger_count == 2
