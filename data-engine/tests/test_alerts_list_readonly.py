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


def test_list_alerts_includes_ticker_for_actionable_history(db):
    """F146: el historial de disparos necesita el ticker para enlazar a la
    investigacion; alertas sin compania devuelven ticker=None, nunca inventado."""
    _seed(db)
    result = list_alerts(ticker=None, status=None, include_snoozed=True, limit=100, db=db)
    tickers = {out.title: out.ticker for out in result}
    assert tickers == {
        "AAPL open": "AAPL",
        "AAPL future": "AAPL",
        "AAPL indefinite": "AAPL",
        "AAPL expired": "AAPL",
    }
    orphan = ResearchAlert(
        company_id=None, alert_type="red_team", severity="medium",
        title="sin compania", message="m", fingerprint="fp-orphan",
        channels=["in_app"], status="open",
    )
    db.add(orphan)
    db.commit()
    result = list_alerts(ticker=None, status=None, include_snoozed=True, limit=100, db=db)
    by_title = {out.title: out for out in result}
    assert by_title["sin compania"].ticker is None


def test_list_alerts_orders_by_real_last_trigger(db):
    """F146: un re-disparo reciente de huella antigua debe salir primero."""
    from app.services.review_alert_service import ReviewAlertService

    service = ReviewAlertService()
    first = service.emit_alert(
        db, company_id=None, alert_type="system", severity="medium",
        title="huella antigua", message="m", fingerprint_parts=["old"],
    )
    service.emit_alert(
        db, company_id=None, alert_type="system", severity="medium",
        title="huella nueva", message="m", fingerprint_parts=["new"],
    )
    # Re-disparo de la huella antigua: su created_at es el mas viejo pero su
    # ultimo disparo es el mas reciente.
    retriggered = service.emit_alert(
        db, company_id=None, alert_type="system", severity="high",
        title="huella antigua", message="m2", fingerprint_parts=["old"],
    )
    assert retriggered.id == first.id
    result = list_alerts(ticker=None, status=None, include_snoozed=True, limit=100, db=db)
    assert [out.title for out in result][:2] == ["huella antigua", "huella nueva"]


def test_list_alerts_exposes_last_triggered_at(db):
    """F146: la hora del disparo que ve la UI sale de last_triggered_at."""
    _seed(db)
    result = list_alerts(ticker=None, status=None, include_snoozed=True, limit=100, db=db)
    for out in result:
        assert out.last_triggered_at is None or out.last_triggered_at >= out.created_at


def test_get_never_mutates_the_orm_rows(db):
    alerts = _seed(db)
    list_alerts(ticker=None, status=None, include_snoozed=False, limit=100, db=db)
    db.expire_all()

    expired = db.scalar(select(ResearchAlert).where(ResearchAlert.id == alerts["expired"].id))
    # La fila sigue como estaba: el GET no escribe (ni commit ni dirty flush).
    assert expired.status == "snoozed"
    assert expired.snoozed_until is not None


def test_list_alerts_resolves_source_url(db):
    """F172: la URL de la fuente sale de metadata.source_url (insider) o del
    NewsEvent enlazado via metadata.news_event_id (filing/noticia); sin URL
    conocida queda None, nunca inventada."""
    from app.models.entities import NewsEvent

    company = Company(
        ticker="AAPL", name="Apple", exchange="NASDAQ", currency="USD",
        sector="Tech", industry="Tech", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.flush()
    event = NewsEvent(
        company_id=company.id, title="AAPL 8-K",
        url="https://www.sec.gov/Archives/edgar/data/1/0001.htm",
    )
    db.add(event)
    db.flush()
    cases = [
        ("insider", {"source_url": "https://www.sec.gov/form4/1"}, "https://www.sec.gov/form4/1"),
        ("filing", {"news_event_id": event.id}, event.url),
        ("sin-fuente", {}, None),
    ]
    for key, metadata, _expected in cases:
        db.add(ResearchAlert(
            company_id=company.id, alert_type="filing", severity="medium",
            title=f"AAPL {key}", message="m", fingerprint=f"fp-src-{key}",
            channels=["in_app"], status="open", metadata_=metadata,
        ))
    db.commit()

    result = list_alerts(ticker=None, status=None, include_snoozed=True, limit=100, db=db)
    urls = {a.title: a.source_url for a in result}
    for key, _metadata, expected in cases:
        assert urls[f"AAPL {key}"] == expected


@pytest.mark.parametrize(
    "bad_url",
    [
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "/relative/path",
        "notaurl",
        "",
        "ftp://example.com/doc",
        "https://[broken/path",
        "https://@/bad",
        "https://:443/path",
    ],
)
def test_list_alerts_source_url_rejects_unsafe_schemes(db, bad_url):
    """F172: source_url alimenta el href de un <a target="_blank">; cualquier
    esquema que no sea http/https absoluto (javascript:, data:, relativo,
    vacio) sale como None tanto desde metadata.source_url como de NewsEvent.url."""
    from app.models.entities import NewsEvent

    company = Company(
        ticker="AAPL", name="Apple", exchange="NASDAQ", currency="USD",
        sector="Tech", industry="Tech", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.flush()
    event = NewsEvent(company_id=company.id, title="t", url=bad_url)
    db.add(event)
    db.flush()
    db.add(ResearchAlert(
        company_id=company.id, alert_type="insider", severity="medium",
        title="meta", message="m", fingerprint=f"fp-bad-meta-{bad_url[:8]}",
        channels=["in_app"], status="open", metadata_={"source_url": bad_url},
    ))
    db.add(ResearchAlert(
        company_id=company.id, alert_type="filing", severity="medium",
        title="news", message="m", fingerprint=f"fp-bad-news-{bad_url[:8]}",
        channels=["in_app"], status="open", metadata_={"news_event_id": event.id},
    ))
    db.commit()

    result = list_alerts(ticker=None, status=None, include_snoozed=True, limit=100, db=db)
    urls = {a.title: a.source_url for a in result}
    assert urls["meta"] is None
    assert urls["news"] is None


def test_list_alerts_source_url_accepts_absolute_http(db):
    """F172: una URL absoluta http/https con host sí sale como enlace, tanto
    desde metadata.source_url como desde NewsEvent.url."""
    from app.models.entities import NewsEvent

    company = Company(
        ticker="AAPL", name="Apple", exchange="NASDAQ", currency="USD",
        sector="Tech", industry="Tech", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.flush()
    good = "https://www.sec.gov/Archives/edgar/data/1/0001.htm"
    event = NewsEvent(company_id=company.id, title="t", url=good)
    db.add(event)
    db.flush()
    db.add(ResearchAlert(
        company_id=company.id, alert_type="filing", severity="medium",
        title="news-ok", message="m", fingerprint="fp-ok-news",
        channels=["in_app"], status="open", metadata_={"news_event_id": event.id},
    ))
    db.commit()

    result = list_alerts(ticker=None, status=None, include_snoozed=True, limit=100, db=db)
    assert result[0].source_url == good


def test_list_alerts_over_http_serves_rows_and_sanitizes():
    """F172: el endpoint HTTP real GET /api/alerts responde 200 con las filas
    (regresión: un helper mal insertado entre el decorador y list_alerts
    dejaba el listado roto aunque la llamada directa pasara) y expone
    source_url ya sanitizado."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    # TestClient sirve la app en otro hilo: StaticPool comparte la unica
    # conexion entre hilos (con :memory: cada conexion seria una BD vacia).
    from sqlalchemy.pool import StaticPool

    from app.api.routes import alerts as alerts_module
    from app.core.database import get_db
    from app.models.entities import NewsEvent

    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.info["tenant_id"] = "tenant-test"
    db = session

    company = Company(
        ticker="AAPL", name="Apple", exchange="NASDAQ", currency="USD",
        sector="Tech", industry="Tech", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.flush()
    event = NewsEvent(
        company_id=company.id, title="t",
        url="https://www.sec.gov/Archives/edgar/data/1/0001.htm",
    )
    db.add(event)
    db.flush()
    db.add(ResearchAlert(
        company_id=company.id, alert_type="filing", severity="medium",
        title="http-ok", message="m", fingerprint="fp-http-ok",
        channels=["in_app"], status="open", metadata_={"news_event_id": event.id},
    ))
    db.add(ResearchAlert(
        company_id=company.id, alert_type="insider", severity="medium",
        title="http-bad", message="m", fingerprint="fp-http-bad",
        channels=["in_app"], status="open", metadata_={"source_url": "javascript:alert(1)"},
    ))
    db.commit()

    app = FastAPI()
    app.include_router(alerts_module.router, prefix="/api/alerts")
    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app)

    response = client.get("/api/alerts")
    assert response.status_code == 200, response.text
    rows = {row["title"]: row for row in response.json()}
    assert rows["http-ok"]["source_url"] == event.url
    assert rows["http-bad"]["source_url"] is None
