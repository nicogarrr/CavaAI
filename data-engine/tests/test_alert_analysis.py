from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.entities import AlertAnalysis, Base, Company, NewsEvent, Position, ResearchAlert, Tenant
from app.services.alert_analysis_service import analyze_alert, queue_analysis, read_analysis
from app.services.tracked_news_alerts import evaluate

NOW = datetime(2026, 9, 27, 12, tzinfo=UTC)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        tenants = [Tenant(external_id=f"analysis-{i}", name=f"Tenant {i}") for i in (1, 2)]
        company = Company(ticker="ASTS", name="AST SpaceMobile", exchange="NASDAQ", currency="USD",
                          company_type="holding", valuation_model="unassigned")
        session.add_all([*tenants, company])
        session.flush()
        session.add(Position(tenant_id=tenants[0].id, company_id=company.id, quantity=Decimal("1")))
        session.commit()
        session.info["tenant_id"] = tenants[0].id
        yield session, tenants, company
    engine.dispose()


def test_gated_alert_caches_honest_analysis_and_is_tenant_isolated(db):
    session, tenants, company = db
    article = NewsEvent(tenant_id=tenants[0].id, company_id=company.id,
                        title="ASTS Company update New ITU filing", source="Publisher",
                        url="https://publisher.example/itu", date=NOW,
                        metadata_={"connector": "rss", "date_source": "source", "source_headline": "ASTS ITU filing submitted"})
    session.add(article)
    session.commit()
    assert evaluate(session, now=NOW)["created"] == 1
    alert = session.scalar(select(ResearchAlert))
    pending = session.scalar(select(AlertAnalysis))
    assert pending and pending.status == "pending"
    assert queue_analysis(session, alert).id == pending.id
    assert analyze_alert(session, alert.id)["status"] == "insufficient_data"
    payload = read_analysis(session, alert.id)
    assert payload["versions"][0]["citations"][0]["excerpt"] == "ASTS ITU filing submitted"
    assert "fuente primaria" in payload["versions"][0]["missing_data"][0].lower()
    assert "Company update New ITU filing" not in str(payload)
    assert analyze_alert(session, alert.id)["analysis_id"] == pending.id
    assert evaluate(session, now=NOW)["created"] == 0
    assert len(session.scalars(select(AlertAnalysis)).all()) == 1
    session.info["tenant_id"] = tenants[1].id
    with pytest.raises(LookupError):
        read_analysis(session, alert.id)
    with pytest.raises(LookupError):
        analyze_alert(session, alert.id)


def test_read_revalidates_source_and_drops_stale_citations(db):
    session, tenants, company = db
    article = NewsEvent(tenant_id=tenants[0].id, company_id=company.id,
                        title="ASTS ITU filing", source="Publisher", url="https://publisher.example/itu",
                        date=NOW, metadata_={"source_headline": "ASTS ITU filing"})
    session.add(article)
    session.flush()
    alert = ResearchAlert(tenant_id=tenants[0].id, company_id=company.id,
                          alert_type="tracked_news", title="Article", message="News", fingerprint="one",
                          metadata_={"news_event_id": article.id})
    session.add(alert)
    session.commit()
    queue_analysis(session, alert)
    analyze_alert(session, alert.id)
    article.metadata_ = {"source_headline": "Different headline"}
    session.commit()
    result = read_analysis(session, alert.id)["versions"][0]
    assert result["citations"] == []
    assert result["status"] == "insufficient_data"


def test_legacy_gdelt_source_date_is_first_seen_not_publication(db):
    session, tenants, company = db
    article = NewsEvent(tenant_id=tenants[0].id, company_id=company.id,
                        title="ASTS ITU filing", source="Publisher", url="https://publisher.example/itu",
                        date=NOW, metadata_={"connector": "gdelt", "date_source": "source",
                                              "source_headline": "ASTS ITU filing"})
    session.add(article)
    session.flush()
    alert = ResearchAlert(tenant_id=tenants[0].id, company_id=company.id,
                          alert_type="tracked_news", title="Article", message="News", fingerprint="gdelt",
                          metadata_={"news_event_id": article.id})
    session.add(alert)
    session.commit()
    queue_analysis(session, alert)
    analyze_alert(session, alert.id)
    citation = read_analysis(session, alert.id)["versions"][0]["citations"][0]
    assert "primera detección GDELT" in citation["as_of"]
    assert "fecha atribuida a la fuente" not in citation["as_of"]


@pytest.mark.parametrize("invalid_headline", [None, 123])
def test_read_bad_headline_type_fails_closed_not_500(db, invalid_headline):
    session, tenants, company = db
    article = NewsEvent(tenant_id=tenants[0].id, company_id=company.id,
                        title="ASTS ITU filing", source="Publisher", url="https://publisher.example/itu",
                        date=NOW, metadata_={"source_headline": "ASTS ITU filing"})
    session.add(article)
    session.flush()
    alert = ResearchAlert(tenant_id=tenants[0].id, company_id=company.id,
                          alert_type="tracked_news", title="Article", message="News", fingerprint="bad-headline",
                          metadata_={"news_event_id": article.id})
    session.add(alert)
    session.commit()
    queue_analysis(session, alert)
    analyze_alert(session, alert.id)
    article.metadata_ = {"source_headline": invalid_headline}
    session.commit()
    result = read_analysis(session, alert.id)["versions"][0]
    assert result["status"] == "insufficient_data"
    assert result["citations"] == [] and result["missing_data"]


def test_later_evaluation_recovers_analysis_row_after_transient_creation_failure(db, monkeypatch):
    session, tenants, company = db
    from app.services import alert_analysis_service
    original = alert_analysis_service.queue_analysis
    attempts = [0]

    def transient(session, alert):
        attempts[0] += 1
        if attempts[0] == 1:
            raise RuntimeError("temporary database failure")
        return original(session, alert)

    monkeypatch.setattr(alert_analysis_service, "queue_analysis", transient)
    session.add(NewsEvent(tenant_id=tenants[0].id, company_id=company.id,
                          title="ASTS ITU filing", source="Publisher",
                          url="https://publisher.example/itu", date=NOW,
                          metadata_={"connector": "rss", "date_source": "source",
                                     "source_headline": "ASTS ITU filing submitted"}))
    session.commit()
    assert evaluate(session, now=NOW)["created"] == 1
    assert session.scalars(select(AlertAnalysis)).all() == []
    assert evaluate(session, now=NOW)["created"] == 0
    assert attempts[0] == 2
    assert len(session.scalars(select(AlertAnalysis)).all()) == 1
    assert len(session.scalars(select(ResearchAlert)).all()) == 1


def test_reconcile_recovers_lost_row_beyond_eligibility_window(db):
    from app.services.alert_analysis_service import reconcile_missing_analyses

    session, tenants, company = db
    old = NOW - timedelta(hours=72)  # fuera de la ventana MAX_AGE de evaluate()
    article = NewsEvent(tenant_id=tenants[0].id, company_id=company.id,
                        title="ASTS Old filing headline", source="Publisher",
                        url="https://publisher.example/old", date=old,
                        metadata_={"connector": "rss", "date_source": "source",
                                   "source_headline": "ASTS old filing submitted"})
    session.add(article)
    session.flush()
    alert = ResearchAlert(tenant_id=tenants[0].id, company_id=company.id, severity="medium",
                          status="open", alert_type="tracked_news", title="t", message="m",
                          fingerprint="fp-old", channels=["in_app"], last_triggered_at=old,
                          metadata_={"news_event_id": article.id, "source_url": article.url,
                                     "source": "Publisher"})
    session.add(alert)
    session.commit()
    # evaluate() no lo recupera: el evento ya no es elegible por antigüedad
    assert evaluate(session, now=NOW)["created"] == 0
    assert session.scalar(select(AlertAnalysis)) is None
    # la reconciliación sí: no depende de la elegibilidad del evento
    stats = reconcile_missing_analyses(session)
    assert stats == {"examined": 1, "queued": 1, "unqueueable": 0, "excluded_no_data": 0}
    row = session.scalar(select(AlertAnalysis))
    assert row and row.status == "pending" and row.alert_id == alert.id
    # idempotente
    assert reconcile_missing_analyses(session) == {
        "examined": 0, "queued": 0, "unqueueable": 0, "excluded_no_data": 0}


def test_reconcile_stays_honest_without_original_headline(db):
    from app.services.alert_analysis_service import reconcile_missing_analyses

    session, tenants, company = db
    article = NewsEvent(tenant_id=tenants[0].id, company_id=company.id,
                        title="ASTS legacy composite", source="Publisher",
                        url="https://publisher.example/legacy", date=NOW,
                        metadata_={"connector": "rss", "date_source": "source"})
    session.add(article)
    session.flush()
    alert = ResearchAlert(tenant_id=tenants[0].id, company_id=company.id, severity="medium",
                          status="open", alert_type="tracked_news", title="t", message="m",
                          fingerprint="fp-legacy", channels=["in_app"], last_triggered_at=NOW,
                          metadata_={"news_event_id": article.id})
    session.add(alert)
    session.commit()
    stats = reconcile_missing_analyses(session)
    # sin titular original no es candidata: el filtro SQL la excluye del lote
    # para que no ocupe sitio cada hora; el gate sigue como autoridad
    assert stats == {"examined": 0, "queued": 0, "unqueueable": 0, "excluded_no_data": 1}
    assert session.scalar(select(AlertAnalysis)) is None


def test_reconcile_unqueueable_backlog_cannot_starve_valid_alert(db):
    from app.services.alert_analysis_service import reconcile_missing_analyses

    session, tenants, company = db
    for i in range(60):
        legacy = NewsEvent(tenant_id=tenants[0].id, company_id=company.id,
                           title=f"legacy {i}", source="Publisher",
                           url="https://publisher.example/legacy", date=NOW,
                           metadata_={"connector": "rss", "date_source": "source"})
        session.add(legacy)
        session.flush()
        session.add(ResearchAlert(tenant_id=tenants[0].id, company_id=company.id,
                                  severity="medium", status="open", alert_type="tracked_news",
                                  title="t", message="m", fingerprint=f"fp-legacy-{i}",
                                  channels=["in_app"], last_triggered_at=NOW,
                                  metadata_={"news_event_id": legacy.id}))
    valid = NewsEvent(tenant_id=tenants[0].id, company_id=company.id,
                      title="valid headline", source="Publisher",
                      url="https://publisher.example/valid", date=NOW,
                      metadata_={"connector": "rss", "date_source": "source",
                                 "source_headline": "ASTS valid headline"})
    session.add(valid)
    session.flush()
    valid_alert = ResearchAlert(tenant_id=tenants[0].id, company_id=company.id,
                                severity="medium", status="open", alert_type="tracked_news",
                                title="t", message="m", fingerprint="fp-valid",
                                channels=["in_app"], last_triggered_at=NOW,
                                metadata_={"news_event_id": valid.id})
    session.add(valid_alert)
    session.commit()
    assert valid_alert.id > max(
        a.id for a in session.scalars(select(ResearchAlert).where(ResearchAlert.id != valid_alert.id)))
    # 60 inencolables delante por ID y limit=50: la válida debe examinarse igual
    stats = reconcile_missing_analyses(session, limit=50)
    assert stats["examined"] == 1 and stats["queued"] == 1
    assert stats["excluded_no_data"] == 60
    row = session.scalar(select(AlertAnalysis))
    assert row and row.alert_id == valid_alert.id and row.status == "pending"
