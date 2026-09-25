"""F17 follow-up: la seleccion de empresas con posiciones para el refresco
intradia no debe hacer DISTINCT sobre la entidad Company completa: en
Postgres rompe con "could not identify an equality operator for type json"
(columnas json: special_sources/special_risks/factor_tags) y el actor
devolvia error en silencio -> 0 filas yahoo_finance_intraday desde #309.
(sqlite no reproduce el error de json; este test fija el comportamiento:
dedup por empresa via subconsulta escalar.)"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, Company, Position
from app.workers import dramatiq_app


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _company(db: Session, ticker: str) -> Company:
    company = Company(
        ticker=ticker, name=f"{ticker} Inc.", exchange="", currency="USD",
        sector="Tech", industry="Tech", company_type="holding",
        valuation_model="unassigned", special_sources=["x"], special_risks=[],
        factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


class _FakeRefreshService:
    seen: list[list[str]] = []

    def __init__(self, price_provider=None):
        pass

    async def refresh(self, db, *, companies):
        type(self).seen.append([c.ticker for c in companies])
        return {"status": "ok", "prices_updated": len(companies)}


def test_intraday_selects_companies_with_positions_deduped(db, monkeypatch):
    aapl = _company(db, "AAPL")
    rklb = _company(db, "RKLB")
    _company(db, "MSFT")  # sin posicion: fuera
    db.add(Position(company_id=aapl.id, tenant_id="tenant-test"))
    db.add(Position(company_id=aapl.id, tenant_id="tenant-test"))  # duplicada
    db.add(Position(company_id=rklb.id, tenant_id="tenant-test"))
    db.commit()

    monkeypatch.setattr(dramatiq_app, "_session", lambda *a, **k: db)
    monkeypatch.setattr(dramatiq_app, "acquire_job_lease", lambda *a, **k: object())
    monkeypatch.setattr(dramatiq_app, "release_job_lease", lambda *a, **k: None)
    monkeypatch.setattr(
        "app.services.market_refresh_service.MarketRefreshService", _FakeRefreshService
    )
    _FakeRefreshService.seen.clear()

    result = dramatiq_app.refresh_portfolio_prices_intraday(1, "user-test")

    assert result.get("status") == "ok", result
    assert _FakeRefreshService.seen == [["AAPL", "RKLB"]]
