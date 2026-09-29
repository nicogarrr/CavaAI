"""Precios a dos velocidades: cartera+watchlist cada ciclo horario,
universo completo a menor cadencia (job scope="universe").

El conjunto tracked lo resuelve _tracked_companies (ya testeado en
test_news_two_speed.py); aqui se prueba que refresh_market_pipeline lo
aplica al refresco de mercado y que el scheduler registra ambas
cadencias.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, Company, Position, WatchItem
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
        ticker=ticker,
        name=f"{ticker} Inc.",
        exchange="",
        currency="USD",
        sector="Tech",
        industry="Tech",
        company_type="holding",
        valuation_model="unassigned",
        special_sources=[],
        special_risks=[],
        factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


class _CapturingRefresh:
    """Sustituto de MarketRefreshService: registra el universo recibido."""

    calls: list = []

    async def refresh(self, db, *, as_of=None, companies=None):
        type(self).calls.append(None if companies is None else [c.ticker for c in companies])
        return {"status": "ok"}


@pytest.fixture
def patched(db, monkeypatch):
    _CapturingRefresh.calls = []
    monkeypatch.setattr(dramatiq_app, "_session", lambda tenant_id, user_id: db)
    monkeypatch.setattr(dramatiq_app, "acquire_job_lease", lambda *a, **k: object())
    monkeypatch.setattr(dramatiq_app, "release_job_lease", lambda *a, **k: None)
    monkeypatch.setattr("app.services.market_refresh_service.MarketRefreshService", _CapturingRefresh)
    return _CapturingRefresh.calls


def test_tracked_scope_refreshes_portfolio_and_watchlist_only(db, patched):
    aapl = _company(db, "AAPL")
    _company(db, "MSFT")
    _company(db, "SAN")
    db.add(Position(company_id=aapl.id, tenant_id="tenant-test"))
    db.add(WatchItem(symbol="SAN.MC", tenant_id="tenant-test"))  # display ticker
    db.commit()
    outcome = dramatiq_app.refresh_market_pipeline.fn(tenant_id=1, user_id="u", scope="tracked")
    assert outcome["scope"] == "tracked"
    assert patched == [["AAPL", "SAN"]]  # SAN.MC resuelve a SAN; MSFT fuera


def test_universe_scope_refreshes_everything(db, patched):
    _company(db, "AAPL")
    _company(db, "MSFT")
    db.commit()
    outcome = dramatiq_app.refresh_market_pipeline.fn(tenant_id=1, user_id="u", scope="universe")
    assert outcome["scope"] == "universe"
    assert patched == [None]  # None = universo completo en refresh()


def test_tracked_empty_does_not_fall_back_to_universe(db, patched):
    _company(db, "AAPL")
    db.commit()
    dramatiq_app.refresh_market_pipeline.fn(tenant_id=1, user_id="u", scope="tracked")
    assert patched == [[]]  # tracked vacio: ninguna llamada, nunca todo el universo


def test_unknown_scope_rejected(db):
    with pytest.raises(ValueError, match="scope"):
        dramatiq_app.refresh_market_pipeline.fn(tenant_id=1, user_id="u", scope="todo")


def test_scheduler_registers_both_cadences():
    from datetime import timedelta

    from app.workers.scheduler import build_scheduler

    scheduler = build_scheduler(background=True)
    jobs = {job.id: job for job in scheduler.get_jobs()}
    assert jobs["market_refresh"].trigger.interval == timedelta(hours=1)
    assert jobs["market_refresh_universe"].trigger.interval == timedelta(hours=6)
