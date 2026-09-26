"""GET /api/alerts: filtro de snooze correcto y respuesta sin mutar el ORM."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api.routes.alerts import list_alerts
from app.models.entities import Base, Company, ResearchAlert


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _seed(db: Session) -> dict[str, ResearchAlert]:
    company = Company(
        ticker="AAPL", name="Apple", exchange="NASDAQ", currency="USD",
        sector="Tech", industry="Tech", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.flush()
    now = datetime.now(UTC)
    alerts = {}
    for key, status, until in [
        ("open", "open", None),
        ("future", "snoozed", now + timedelta(hours=2)),
        ("indefinite", "snoozed", None),
        ("expired", "snoozed", now - timedelta(hours=2)),
    ]:
        alert = ResearchAlert(
            company_id=company.id, alert_type="price_above", severity="high",
            title=f"AAPL {key}", message="m", fingerprint=f"fp-{key}",
            channels=["in_app"], status=status, snoozed_until=until,
        )
        db.add(alert)
        alerts[key] = alert
    db.commit()
    return alerts


def test_snooze_indefinite_stays_hidden_and_expired_reappears(db):
    _seed(db)
    result = list_alerts(ticker=None, status=None, include_snoozed=False, limit=100, db=db)
    by_title = {a.title: a for a in result}

    assert "AAPL open" in by_title
    # Snooze activo (futuro) e indefinido (sin fecha): ocultos por defecto.
    assert "AAPL future" not in by_title
    assert "AAPL indefinite" not in by_title
    # Snooze caducado: reaparece como 'open' derivado.
    assert by_title["AAPL expired"].status == "open"
    assert by_title["AAPL expired"].snoozed_until is None

    # Con include_snoozed=True salen todas.
    everything = list_alerts(ticker=None, status=None, include_snoozed=True, limit=100, db=db)
    assert {a.title for a in everything} == {
        "AAPL open", "AAPL future", "AAPL indefinite", "AAPL expired",
    }


def test_get_never_mutates_the_orm_rows(db):
    alerts = _seed(db)
    list_alerts(ticker=None, status=None, include_snoozed=False, limit=100, db=db)
    db.expire_all()

    expired = db.scalar(select(ResearchAlert).where(ResearchAlert.id == alerts["expired"].id))
    # La fila sigue como estaba: el GET no escribe (ni commit ni dirty flush).
    assert expired.status == "snoozed"
    assert expired.snoozed_until is not None
