"""D3: la API del retorno realizado por HTTP.

Se monta el router real sobre una BD en memoria con ``StaticPool`` (el
``TestClient`` sirve en otro hilo) y se comprueba el contrato de la respuesta:
español, ``N/D`` con motivo, hit-rate con denominador, y recálculo idempotente.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.routes import thesis_realized_return as route_module
from app.core.database import get_db
from app.models import Company, MarketPrice, ThesisVersion
from app.models.entities import Base
from app.services.thesis_realized_return_service import ThesisRealizedReturnService

PUBLISHED = dt.datetime(2023, 1, 2, 9, 0, tzinfo=dt.UTC)
ENTRY_DAY = dt.date(2023, 1, 2)
AS_OF = dt.date(2025, 12, 31)
PREFIX = "/api/thesis-realized-return"


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.info["tenant_id"] = 1
    yield session
    session.close()


@pytest.fixture
def client(db):
    app = FastAPI()
    app.include_router(route_module.router, prefix=PREFIX)

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    with TestClient(app) as test_client:
        yield test_client


def _seed(
    db: Session,
    ticker: str,
    *,
    drift: float = 0.0008,
    published: dt.datetime = PUBLISHED,
    days: int | None = None,
) -> ThesisVersion:
    # La serie llega hasta hoy: una tesis de hace diez días tiene que tener precio
    # de entrada, o "demasiado pronto" se disfrazaría de "sin precio".
    days = days if days is not None else (dt.date.today() - ENTRY_DAY).days + 2
    company = Company(
        ticker=ticker,
        name=f"{ticker} Co",
        exchange="NASDAQ",
        currency="USD",
        sector="Industrials",
        industry="Test",
        company_type="standard",
        valuation_model="standard_dcf",
        special_sources=[],
        special_risks=[],
        factor_tags=[],
    )
    db.add(company)
    db.flush()
    _ensure_benchmark(db, days=days)
    for index in range(days):
        value = Decimal(str(round(100 * (1 + drift * index), 6)))
        db.add(
            MarketPrice(
                company_id=company.id,
                date=ENTRY_DAY + dt.timedelta(days=index),
                close=value,
                adj_close=value,
                source="test",
            )
        )
    thesis = ThesisVersion(
        company_id=company.id,
        version=1,
        status="published",
        thesis_markdown="La tesis",
        executive_summary="Resumen",
        rating="buy",
        expected_value=Decimal("150"),
        created_at=published,
        updated_at=published,
    )
    db.add(thesis)
    db.commit()
    return thesis


def _ensure_benchmark(db: Session, days: int = 1100) -> Company:
    """El S&P 500 del repo, creado una sola vez y con su serie ajustada."""
    company = db.query(Company).filter(Company.ticker == "^GSPC").one_or_none()
    if company is None:
        company = Company(
            ticker="^GSPC",
            name="S&P 500",
            exchange="INDEX",
            currency="USD",
            sector="Index",
            industry="Index",
            company_type="index",
            valuation_model="none",
            special_sources=[],
            special_risks=[],
            factor_tags=[],
        )
        db.add(company)
        db.flush()
        for index in range(days):
            value = Decimal(str(round(4000 * (1 + 0.0004 * index), 6)))
            db.add(
                MarketPrice(
                    company_id=company.id,
                    date=ENTRY_DAY + dt.timedelta(days=index),
                    close=value,
                    adj_close=value,
                    source="idx-test",
                )
            )
        db.commit()
    return company


def _recompute(client: TestClient, ticker: str) -> dict:
    response = client.post(f"{PREFIX}/recompute", json={"ticker": ticker})
    assert response.status_code == 200, response.text
    return response.json()

def test_unknown_ticker_is_404(client: TestClient) -> None:
    assert client.get(f"{PREFIX}?ticker=NOPE").status_code == 404


def test_reading_before_computing_is_404(client: TestClient, db: Session) -> None:
    _seed(db, "HUELO")
    assert client.get(f"{PREFIX}?ticker=HUELO").status_code == 404


def test_recompute_then_read_by_ticker(client: TestClient, db: Session) -> None:
    thesis = _seed(db, "HTTP1")

    payload = _recompute(client, "HTTP1")
    assert payload["recomputados"] == 1
    assert payload["actualizados"] == 1
    assert payload["resultados"][0]["veredicto"]["outcome"] == "thesis_right"

    response = client.get(f"{PREFIX}?ticker=HTTP1")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ticker"] == "HTTP1"
    assert body["casos"] == 1
    record = body["resultados"][0]
    assert record["thesis_id"] == thesis.id
    assert record["veredicto"]["outcome"] == "thesis_right"
    assert record["veredicto"]["cuenta_en_hit_rate"] is True
    assert [item["horizonte"] for item in record["horizontes"]] == ["1M", "3M", "6M", "1A", "2A"]
    assert record["horizontes"][0]["retorno_realizado"]["valor"] != "N/D"
    assert "inconclusive" in body["definiciones_veredicto"]


def test_recompute_is_idempotent_over_http(client: TestClient, db: Session) -> None:
    _seed(db, "HTTP2")

    first = _recompute(client, "HTTP2")
    second = _recompute(client, "HTTP2")

    assert first["actualizados"] == 1
    assert second["actualizados"] == 0
    assert second["sin_cambios"] == 1
    assert first["resultados"][0]["price_fingerprint"] == second["resultados"][0][
        "price_fingerprint"
    ]
    assert second["resultados"][0]["revision"] == 1


def test_read_one_thesis_by_id(client: TestClient, db: Session) -> None:
    thesis = _seed(db, "HTTP3")
    _recompute(client, "HTTP3")

    response = client.get(f"{PREFIX}/{thesis.id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["thesis_id"] == thesis.id
    assert body["ticker"] == "HTTP3"
    assert body["horizonte_de_juicio"]["dias"] == 180


def test_unknown_thesis_is_404(client: TestClient) -> None:
    assert client.get(f"{PREFIX}/999999").status_code == 404


def test_portfolio_endpoint_is_not_shadowed_by_the_thesis_id_route(
    client: TestClient, db: Session
) -> None:
    _seed(db, "HTTP4")
    _seed(db, "HTTP5", drift=-0.001)
    _recompute(client, "HTTP4")
    _recompute(client, "HTTP5")

    response = client.get(f"{PREFIX}/portfolio")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["casos_totales"] == 2
    assert body["denominador_hit_rate"] == 2
    assert body["conteo"]["thesis_right"] == 1
    assert body["conteo"]["thesis_wrong"] == 1
    assert "2 tesis juzgadas" in body["hit_rate_texto"]
    assert body["retorno_realizado_por_horizonte"]["6M"]["n"] == 2
    assert body["benchmark"] == "^GSPC"


def test_portfolio_summary_exposes_the_excluded_cases(client: TestClient, db: Session) -> None:
    # La ruta usa el día de hoy, así que "demasiado pronto" se construye con una
    # tesis de hace diez días: su horizonte de 6M todavía no ha vencido.
    fresh = (dt.datetime.now(dt.UTC) - dt.timedelta(days=10)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    _seed(db, "HTTP6")
    _seed(db, "HTTP7", published=fresh)
    _recompute(client, "HTTP6")
    _recompute(client, "HTTP7")

    body = client.get(f"{PREFIX}/portfolio").json()

    assert body["casos_totales"] == 2
    assert body["conteo"]["too_early"] == 1
    assert body["excluidos_del_hit_rate"]["too_early"] == 1
    assert body["denominador_hit_rate"] == 1


def test_portfolio_recompute_without_ticker_reports_the_scope(client: TestClient, db: Session) -> None:
    _seed(db, "HTTP8")
    _seed(db, "HTTP9")

    response = client.post(f"{PREFIX}/recompute", json={})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ambito"] == "todas las tesis del tenant"
    assert body["recomputados"] == 2
    assert body["actualizados"] == 2
    assert body["truncado"] is False
    assert body["agregado"]["casos_totales"] == 2
    assert client.post(f"{PREFIX}/recompute", json={}).json()["actualizados"] == 0


def test_recompute_of_a_ticker_without_thesis_is_404(client: TestClient, db: Session) -> None:
    db.add(
        Company(
            ticker="HUERFANO",
            name="Huerfano Co",
            exchange="NASDAQ",
            currency="USD",
            sector="Industrials",
            industry="Test",
            company_type="standard",
            valuation_model="standard_dcf",
            special_sources=[],
            special_risks=[],
            factor_tags=[],
        )
    )
    db.commit()
    assert client.post(f"{PREFIX}/recompute", json={"ticker": "HUERFANO"}).status_code == 404


def test_unmeasured_numbers_come_back_as_nd_with_a_reason(
    client: TestClient, db: Session
) -> None:
    _seed(db, "HTTP10")
    _recompute(client, "HTTP10")

    record = client.get(f"{PREFIX}?ticker=HTTP10").json()["resultados"][0]
    # La cartera cotiza en EUR: sin tipos de cambio fechados el retorno en
    # moneda base no se inventa, aunque el retorno local sí se mide.
    assert record["moneda_base"] == "EUR"
    six = next(item for item in record["horizontes"] if item["horizonte"] == "6M")
    assert six["retorno_realizado"]["valor"] != "N/D"
    assert six["retorno_realizado_base"]["valor"] == "N/D"
    assert "EUR/USD" in six["retorno_realizado_base"]["motivo"]
    # Activo e índice en USD: las dos piernas ya son comparables y el alfa se
    # mide sin FX, aunque el retorno absoluto en moneda base siga siendo N/D.
    assert six["alfa"]["valor"] != "N/D"
    assert six["alfa"]["motivo"] is None
    assert record["leccion"]["decision_lesson_id"] == "N/D"
    assert record["leccion"]["motivo"]


def test_alpha_is_nd_when_the_benchmark_cannot_be_put_in_the_same_base(
    client: TestClient, db: Session
) -> None:
    company = db.query(Company).filter(Company.ticker == "EURCO").one_or_none()
    if company is None:
        company = Company(
            ticker="EURCO",
            name="Euro Co",
            exchange="BME",
            currency="EUR",
            sector="Industrials",
            industry="Test",
            company_type="standard",
            valuation_model="standard_dcf",
            special_sources=[],
            special_risks=[],
            factor_tags=[],
        )
        db.add(company)
        db.flush()
        _ensure_benchmark(db)
        for index in range((dt.date.today() - ENTRY_DAY).days + 2):
            value = Decimal(str(round(90 * (1 + 0.0008 * index), 6)))
            db.add(
                MarketPrice(
                    company_id=company.id,
                    date=ENTRY_DAY + dt.timedelta(days=index),
                    close=value,
                    adj_close=value,
                    source="test",
                )
            )
    thesis = ThesisVersion(
        company_id=company.id,
        version=1,
        status="published",
        thesis_markdown="La tesis",
        executive_summary="Resumen",
        rating="buy",
        expected_value=Decimal("110"),
        created_at=PUBLISHED,
        updated_at=PUBLISHED,
    )
    db.add(thesis)
    db.commit()
    _recompute(client, "EURCO")

    record = client.get(f"{PREFIX}?ticker=EURCO").json()["resultados"][0]
    six = next(item for item in record["horizontes"] if item["horizonte"] == "6M")
    assert record["divisa"] == "EUR"
    assert six["retorno_realizado_base"]["valor"] != "N/D"
    assert six["alfa"]["valor"] == "N/D"
    assert "EUR/USD" in six["alfa"]["motivo"]


def test_tenant_scope_is_kept_over_http(client: TestClient, db: Session) -> None:
    _seed(db, "HTTP11")
    _recompute(client, "HTTP11")

    db.info["tenant_id"] = 2
    assert client.get(f"{PREFIX}?ticker=HTTP11").status_code == 404
    assert client.get(f"{PREFIX}/portfolio").json()["casos_totales"] == 0


def test_service_recompute_for_company_matches_the_route(client: TestClient, db: Session) -> None:
    thesis = _seed(db, "HTTP12")
    _recompute(client, "HTTP12")

    company = db.query(Company).filter(Company.ticker == "HTTP12").one()
    rows = ThesisRealizedReturnService().recompute_for_company(db, company)

    assert [row.thesis_version_id for row in rows] == [thesis.id]
