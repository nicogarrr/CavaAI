"""ReviewAlertService contract tests.

Reviews dedupe by open status + owning object; alerts dedupe by
fingerprint and reopen honestly from resolved; severity mapping and
state transitions are deterministic.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.models.entities import (
    Base,
    Claim,
    Company,
    ResearchAlert,
    ResearchReview,
    ThesisChange,
)
from app.services.review_alert_service import ReviewAlertService, _severity


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _company(db: Session) -> Company:
    company = Company(
        ticker="AAPL", name="Apple", exchange="NASDAQ", currency="USD",
        sector="Tech", industry="Tech", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


def test_severity_mapping():
    assert _severity(9, negative=True) == "critical"
    assert _severity(9, negative=False) == "high"  # critical requires negative
    assert _severity(8) == "high"
    assert _severity(5) == "medium"
    assert _severity(4) == "low"


def test_create_review_dedupes_open_review_and_alert(db):
    company = _company(db)
    service = ReviewAlertService()
    first = service.create_review(
        db, review_type="thesis_update", title="Review required: thesis update",
        summary="s", company_id=company.id, materiality_score=8,
    )
    assert first.priority == "high"
    alerts = db.scalars(select(ResearchAlert)).all()
    assert len(alerts) == 1
    assert alerts[0].review_id == first.id
    assert alerts[0].severity == "high"
    assert alerts[0].status == "open"
    assert alerts[0].channels == ["in_app"]

    second = service.create_review(
        db, review_type="thesis_update", title="Review required: thesis update",
        summary="s", company_id=company.id, materiality_score=8,
    )
    assert second.id == first.id
    assert db.scalar(select(func.count()).select_from(ResearchReview)) == 1
    assert db.scalar(select(func.count()).select_from(ResearchAlert)) == 1


def test_create_from_change_skips_when_review_not_required(db):
    company = _company(db)
    change = ThesisChange(
        company_id=company.id, change_type="update", summary="minor",
        requires_review=False,
    )
    db.add(change)
    db.commit()
    assert ReviewAlertService().create_from_change(db, change) is None
    assert db.scalar(select(func.count()).select_from(ResearchReview)) == 0


def test_create_from_claim_marks_contradicted_negative(db):
    company = _company(db)
    claim = Claim(company_id=company.id, statement="c", materiality_score=9)
    db.add(claim)
    db.commit()
    review = ReviewAlertService().create_from_claim(db, claim, "contradicted", "evidence contra")
    assert review.review_type == "claim_contradicted"
    assert review.priority == "critical"  # 9 + negative
    assert review.claim_id == claim.id


def test_emit_alert_dedupes_by_fingerprint_and_reopens_resolved(db):
    service = ReviewAlertService()
    alert = service.emit_alert(
        db, company_id=None, alert_type="system", severity="medium",
        title="t", message="first", fingerprint_parts=["a", "b"],
    )
    again = service.emit_alert(
        db, company_id=None, alert_type="system", severity="high",
        title="t", message="second", fingerprint_parts=["a", "b"],
    )
    assert again.id == alert.id
    assert again.message == "second"  # updated in place, no duplicate
    assert again.severity == "high"
    assert db.scalar(select(func.count()).select_from(ResearchAlert)) == 1

    service.transition_alert(alert, action="resolve", actor="tester")
    assert alert.status == "resolved"
    assert alert.resolved_at is not None

    revived = service.emit_alert(
        db, company_id=None, alert_type="system", severity="medium",
        title="t", message="third", fingerprint_parts=["a", "b"],
    )
    assert revived.status == "open"
    assert revived.resolved_at is None


def test_transition_alert_actions(db):
    service = ReviewAlertService()
    alert = ResearchAlert(
        company_id=None, severity="low", status="open", alert_type="t",
        title="t", message="m", fingerprint="fp1", channels=["in_app"],
    )
    db.add(alert)
    db.commit()

    service.transition_alert(alert, action="acknowledge", actor="nico")
    assert alert.status == "acknowledged"
    assert alert.acknowledged_by == "nico"
    assert alert.acknowledged_at is not None

    with pytest.raises(ValueError):
        service.transition_alert(alert, action="snooze", actor="nico",
                                 snoozed_until=datetime.now(UTC) - timedelta(minutes=1))
    future = datetime.now(UTC) + timedelta(hours=2)
    service.transition_alert(alert, action="snooze", actor="nico", snoozed_until=future)
    assert alert.status == "snoozed"
    assert alert.snoozed_until == future

    service.transition_alert(alert, action="reopen", actor="nico")
    assert alert.status == "open"
    assert alert.snoozed_until is None

    with pytest.raises(ValueError):
        service.transition_alert(alert, action="explode", actor="nico")


def test_transition_review_sets_status_and_notes(db):
    review = ResearchReview(
        company_id=None, review_type="t", status="open", priority="low",
        title="t", summary="s",
    )
    db.add(review)
    db.commit()
    ReviewAlertService().transition_review(review, status="resolved", resolution_notes="done")
    assert review.status == "resolved"
    assert review.resolution_notes == "done"
