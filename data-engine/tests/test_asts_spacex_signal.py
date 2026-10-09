from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.entities import Base, Company, NewsEvent, Position, ResearchAlert, Tenant, WatchItem
from app.services.asts_spacex_signal import evaluate, matches

NOW = datetime(2026, 10, 9, 18, tzinfo=UTC)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    engine.dispose()


def test_matches_requires_spacex_actor_and_positive_closed_deal():
    assert matches("SpaceX signs agreement with Verizon for Starlink Mobile")
    assert matches("Starlink Mobile alcanza un acuerdo con Telefónica")
    assert matches("Vodafone signs deal with Starlink")
    assert not matches("SpaceX launches Starlink satellites")
    assert not matches("Verizon signs agreement with AST SpaceMobile")
    assert not matches("SpaceX deal with a small regional carrier")
    assert not matches(None)
    assert not matches("Tim Cook signs agreement with SpaceX")


def test_matches_rejects_denials_cancellations_plans_and_ast_deals():
    assert not matches("SpaceX denies agreement with Verizon")
    assert not matches("SpaceX deal with Verizon cancelled")
    assert not matches("SpaceX and T-Mobile talks on a direct-to-cell deal")
    assert not matches("SpaceX plans agreement with Vodafone")
    assert not matches("SpaceX may sign deal with AT&T, sources say")
    assert not matches("SpaceX niega un acuerdo con Telefónica")
    assert not matches("Verizon signs agreement with AST SpaceMobile as SpaceX faces delays")
    assert not matches("Direct-to-cell agreement signed with Verizon")  # sin actor SpaceX
    assert not matches("SpaceX launches rockets. Verizon signs agreement with Nokia")  # otra oracion


def _setup(db, *, watch=True):
    t1 = Tenant(external_id="sig-1", name="One", status="active", metadata_={})
    t2 = Tenant(external_id="sig-2", name="Two", status="active", metadata_={})
    db.add_all((t1, t2))
    db.flush()
    a = Company(ticker="ASTS", name="AST", exchange="NASDAQ", currency="USD", company_type="holding", valuation_model="unassigned")
    s = Company(ticker="SPCX", name="SpaceX", exchange="NASDAQ", currency="USD", company_type="holding", valuation_model="unassigned")
    db.add_all((a, s))
    db.flush()
    if watch:
        db.add(WatchItem(tenant_id=t1.id, symbol="ASTS"))
    db.commit()
    return t1, t2, a, s


def _news(db, tenant, company, title, url, *, published=NOW - timedelta(hours=3), meta=None):
    db.add(NewsEvent(tenant_id=tenant.id, company_id=company.id, title=title, source="publisher.example", url=url,
                     date=published, metadata_=meta if meta is not None else {"date_source": "source", "connector": "rss", "source_headline": title}))
    db.commit()


def test_alert_created_once_cited_and_tenant_isolated(db):
    t1, t2, a, s = _setup(db)
    _news(db, t1, s, "SpaceX signs agreement with Verizon for Starlink Mobile", "https://publisher.example/x")
    _news(db, t2, s, "SpaceX signs agreement with Vodafone", "https://publisher.example/y")
    db.info["tenant_id"] = t1.id
    assert evaluate(db, now=NOW)["created"] == 1
    assert evaluate(db, now=NOW)["created"] == 0
    alert = db.scalars(select(ResearchAlert)).one()
    assert alert.tenant_id == t1.id and alert.company_id == a.id
    assert alert.alert_type == "asts_spacex_mno_signal" and alert.severity == "high"
    assert alert.metadata_["source_url"] == "https://publisher.example/x"
    assert "no confirma" in alert.message
    db.info["tenant_id"] = t2.id
    assert evaluate(db, now=NOW)["created"] == 0  # t2 no sigue ASTS


def test_untrusted_old_or_untracked_do_not_alert(db):
    t1, _, a, s = _setup(db)
    title = "SpaceX signs agreement with Verizon"
    _news(db, t1, s, title, "https://publisher.example/old", published=NOW - timedelta(days=5))
    _news(db, t1, s, title, "https://publisher.example/manual", meta={"connector": "manual", "date_source": "source", "source_headline": title})
    _news(db, t1, s, title, "https://publisher.example/nodate", meta={"connector": "rss", "date_source": "fallback", "source_headline": title})
    db.info["tenant_id"] = t1.id
    assert evaluate(db, now=NOW)["created"] == 0
    assert db.scalars(select(ResearchAlert)).all() == []


def test_holder_without_watchlist_is_tracked(db):
    t1, _, a, s = _setup(db, watch=False)
    db.add(Position(tenant_id=t1.id, company_id=a.id, quantity=Decimal("1")))
    db.commit()
    _news(db, t1, a, "Starlink Mobile partners with Telstra", "https://publisher.example/z")
    db.info["tenant_id"] = t1.id
    assert evaluate(db, now=NOW)["created"] == 1


def test_title_fallback_is_not_used(db):
    t1, _, a, s = _setup(db)
    title = "SpaceX signs agreement with Verizon"
    # Sin source_headline textual del conector: aunque el titulo coincida, no hay senal.
    _news(db, t1, s, title, "https://publisher.example/nosrc", meta={"connector": "rss", "date_source": "source"})
    db.info["tenant_id"] = t1.id
    assert evaluate(db, now=NOW)["created"] == 0


def test_url_without_host_and_gdelt_distinction(db):
    t1, _, a, s = _setup(db)
    title = "SpaceX signs agreement with Verizon"
    _news(db, t1, s, title, "https://", meta={"connector": "rss", "date_source": "source", "source_headline": title})
    _news(db, t1, s, title, "https://publisher.example/g", meta={"connector": "gdelt", "date_source": "source", "source_headline": title})
    db.info["tenant_id"] = t1.id
    assert evaluate(db, now=NOW)["created"] == 1
    alert = db.scalars(select(ResearchAlert)).one()
    assert "detectado por GDELT" in alert.message and alert.metadata_["date_source"] == "gdelt_first_seen"
    assert alert.metadata_["source_url"] == "https://publisher.example/g"
