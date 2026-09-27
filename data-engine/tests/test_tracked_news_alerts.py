from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.entities import Base, Company, NewsEvent, Position, ResearchAlert, Tenant, WatchItem
from app.services.tracked_news_alerts import evaluate

NOW = datetime(2026, 9, 27, 12, tzinfo=UTC)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    engine.dispose()


def _setup(db):
    t1 = Tenant(external_id="tracked-1", name="One", status="active", metadata_={})
    t2 = Tenant(external_id="tracked-2", name="Two", status="active", metadata_={})
    db.add_all((t1, t2))
    db.flush()
    a = Company(ticker="ASTS", name="AST", exchange="NASDAQ", currency="USD",
                company_type="holding", valuation_model="unassigned")
    b = Company(ticker="WATCH", name="Watch", exchange="NASDAQ", currency="USD",
                company_type="holding", valuation_model="unassigned")
    db.add_all((a, b))
    db.flush()
    db.add(Position(tenant_id=t1.id, company_id=a.id, quantity=Decimal("1")))
    db.add(WatchItem(tenant_id=t1.id, symbol="WATCH"))
    db.add(WatchItem(tenant_id=t2.id, symbol="ASTS"))
    db.commit()
    return t1, t2, a, b


def _news(db, tenant, company, title, url, *, published=NOW - timedelta(hours=2), metadata=None):
    row = NewsEvent(tenant_id=tenant.id, company_id=company.id, title=title, source="publisher.example",
                    url=url, date=published, metadata_=metadata if metadata is not None else {"date_source": "source"})
    db.add(row)
    db.commit()
    return row


def test_in_app_held_and_watchlist_with_citation_and_dedup(db):
    t1, t2, a, b = _setup(db)
    _news(db, t1, a, "ASTS ITU filing submitted", "https://publisher.example/asts")
    _news(db, t1, b, "WATCH earnings report", "https://publisher.example/watch")
    _news(db, t2, a, "ASTS acquisition report", "https://publisher.example/other")
    db.info["tenant_id"] = t1.id
    result = evaluate(db, now=NOW)
    assert result["created"] == 2
    alerts = db.scalars(select(ResearchAlert).order_by(ResearchAlert.id)).all()
    assert len(alerts) == 2
    assert all(row.channels == ["in_app"] and row.alert_type == "tracked_news" for row in alerts)
    assert {row.metadata_["matching"][0] for row in alerts} == {"cartera", "watchlist"}
    assert {row.metadata_["source_url"] for row in alerts} == {
        "https://publisher.example/asts", "https://publisher.example/watch"}
    assert evaluate(db, now=NOW)["created"] == 0
    db.info["tenant_id"] = t2.id
    assert evaluate(db, now=NOW)["created"] == 1
    assert len(db.scalars(select(ResearchAlert)).all()) == 1


def test_no_unknown_date_url_or_untracked_and_cooldown(db):
    t1, _, a, b = _setup(db)
    _news(db, t1, a, "ASTS ITU filing submitted", "https://publisher.example/asts")
    _news(db, t1, a, "ASTS results", "https://publisher.example/second")
    _news(db, t1, a, "ASTS filing", "javascript:alert(1)")
    _news(db, t1, b, "WATCH filing", "https://publisher.example/fallback",
          metadata={"date_source": "ingested_at_fallback"})
    _news(db, t1, a, "ASTS filing", "https://publisher.example/old", published=NOW-timedelta(days=5))
    c = Company(ticker="OTHER", name="Other", exchange="NASDAQ", currency="USD",
                company_type="holding", valuation_model="unassigned")
    db.add(c)
    db.commit()
    _news(db, t1, c, "OTHER filing", "https://publisher.example/untracked")
    db.info["tenant_id"] = t1.id
    result = evaluate(db, now=NOW)
    assert result["created"] == 1
    assert result["cooldown_skips"] == 1
    assert len(db.scalars(select(ResearchAlert)).all()) == 1
    # A previously suppressed source may not burst out when the cooldown expires.
    assert evaluate(db, now=NOW + timedelta(hours=7))["created"] == 0


def test_no_tenant_context_fails_closed(db):
    with pytest.raises(ValueError):
        evaluate(db, now=NOW)


def test_gdelt_first_seen_is_not_claimed_as_publication_date(db):
    tenant, _, company, _ = _setup(db)
    _news(db, tenant, company, "ASTS ITU filing", "https://publisher.example/itu",
          metadata={"connector": "gdelt", "date_source": "source"})
    db.info["tenant_id"] = tenant.id
    assert evaluate(db, now=NOW)["created"] == 1
    alert = db.scalar(select(ResearchAlert))
    assert "detectada por GDELT" in alert.message
    assert "publicó el" not in alert.message
    assert alert.metadata_["date_source"] == "gdelt_first_seen"
