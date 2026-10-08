import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.llm import LLMResponse, Message, Usage
from app.models import Tenant
from app.models.entities import BudgetUsage, Company, NewsEvent
from app.models.paper_trading import PaperTrade
from app.services import llm_proposal_runner as runner
from app.services.llm_proposal_service import ProposalRejected

NOW = datetime(2026, 10, 8, 12, tzinfo=UTC)


def good(**over):
    base = {
        "direction": "long", "horizon": "short",
        "thesis": "El contrato nuevo mejora la visibilidad de ingresos del proximo trimestre.",
        "conviction": 0.6, "entry": 99.0, "stop": 92.0, "target": 115.0,
        "evidence_ids": ["news:1"],
        "inference_basis": "Inferencia mia: el contrato se traduce en ingresos recurrentes.",
    }
    base.update(over)
    return base


class Provider:
    name = "stub"

    def __init__(self, *outs):
        self.outs, self.calls = list(outs), 0

    async def complete(self, request):
        self.calls += 1
        out = self.outs.pop(0)
        return LLMResponse(Message("assistant", out if isinstance(out, str) else json.dumps(out)),
                           Usage(10, 10, 20), "m", "p")


def quote(currency="USD"):
    return lambda ticker: {"live_c": 100.0, "live_t": NOW.timestamp() - 60, "currency": currency}


@pytest.fixture
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        session.add_all([Tenant(id=1, external_id="w-1"), Tenant(id=2, external_id="w-2")])
        session.commit()
        session.info["tenant_id"] = 1
        session.add(Company(id=1, ticker="AAPL", name="Apple", exchange="NASDAQ",
                            company_type="large_cap", valuation_model="dcf"))
        session.add(NewsEvent(id=1, company_id=1, date=NOW - timedelta(days=1),
                              title="Apple firma un contrato de suministro", source="Reuters"))
        session.commit()
        yield session
    engine.dispose()


def run(db, provider, ticker="AAPL", **kw):
    kw.setdefault("fetch_quote", quote())
    return asyncio.run(runner.generate_proposal(db, ticker, provider=provider, now=NOW, **kw))


def test_generates_and_stores_proposal_with_currency_and_budget(db):
    row = run(db, Provider(good()))
    assert row.status == "pending" and row.author == "LLM" and row.currency == "USD"
    assert row.proposal_key.startswith("llm:AAPL:")
    assert db.scalar(select(func.count(BudgetUsage.id)).where(BudgetUsage.workflow == "llm_proposal")) == 1


def test_unknown_company_and_no_recent_news_never_call_the_model(db):
    p = Provider(good())
    with pytest.raises(ProposalRejected, match="empresa_no_seguida"):
        run(db, p, ticker="ZZZZ")
    db.get(NewsEvent, 1).date = NOW - timedelta(days=40)
    db.commit()
    with pytest.raises(ProposalRejected, match="sin_titulares"):
        run(db, p)
    assert p.calls == 0


def test_missing_quote_fails_closed_without_model_call(db):
    p = Provider(good())

    def boom(_):
        raise RuntimeError("yahoo caido")

    with pytest.raises(ProposalRejected, match="sin_cotizacion"):
        run(db, p, fetch_quote=boom)
    assert p.calls == 0 and db.scalar(select(func.count(PaperTrade.id))) == 0


def test_disabled_provider_and_bad_ticker(db):
    class Off(Provider):
        name = "disabled"

    with pytest.raises(ProposalRejected, match="llm_deshabilitado"):
        run(db, Off())
    with pytest.raises(ProposalRejected, match="ticker_invalido"):
        run(db, Provider(), ticker="../x")


def test_daily_quota_blocks_before_calling_the_model(db):
    for i in range(runner.DAILY_QUOTA):
        db.add(PaperTrade(proposal_key=f"llm:AAPL:20261008:{i}", ticker="AAPL", direction="long",
                          horizon="short", thesis="t" * 30, conviction=0.5, proposed_entry=99,
                          stop=92, target=115, quantity=1, inference_basis="i" * 20,
                          status="pending", created_at=NOW - timedelta(hours=1)))
    db.commit()
    p = Provider(good())
    with pytest.raises(runner.QuotaExceeded):
        run(db, p)
    assert p.calls == 0


def test_budget_exhausted_blocks_before_calling_the_model(db, monkeypatch):
    monkeypatch.setattr(runner.BudgetController, "can_spend", lambda self, db, cost: False)
    p = Provider(good())
    with pytest.raises(ProposalRejected, match="presupuesto_agotado"):
        run(db, p)
    assert p.calls == 0


def test_endpoint_creates_and_maps_rejections(db, monkeypatch):
    from app.api.routes.paper_trading import router
    from app.core.database import get_db

    app = FastAPI()
    app.include_router(router, prefix="/paper-trading")
    app.dependency_overrides[get_db] = lambda: db
    db.get(NewsEvent, 1).date = datetime.now(UTC) - timedelta(days=1)
    db.commit()
    monkeypatch.setattr(runner, "create_llm_provider", lambda: Provider(good()))
    monkeypatch.setattr(
        "app.api.routes.market.market_quote",
        lambda t: {"live_c": 100.0, "live_t": datetime.now(UTC).timestamp() - 60, "currency": "USD"},
    )
    client = TestClient(app)
    assert client.post("/paper-trading/llm-proposals", json={"ticker": "ZZZZ"}).status_code == 422
    assert client.post("/paper-trading/llm-proposals", json={"ticker": "AAPL", "x": 1}).status_code == 422
    created = client.post("/paper-trading/llm-proposals", json={"ticker": "aapl"})
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "pending" and created.json()["currency"] == "USD"


def test_no_transaction_is_held_during_either_llm_call_including_retry(db):
    seen = []

    class Spy(Provider):
        async def complete(self, request):
            seen.append(db.in_transaction())
            return await super().complete(request)

    cjk = good(thesis="El contrato \u4e2d\u6587\u6a21\u578b mejora la visibilidad de ingresos del trimestre.")
    row = run(db, Spy(cjk, good()))
    assert row.status == "pending"
    assert seen == [False, False]


def test_retry_budget_denial_releases_the_transaction(db, monkeypatch):
    seen = []
    calls = {"n": 0}
    real = runner.BudgetController.can_spend

    def deny_second(self, session, cost):
        calls["n"] += 1
        ok = real(self, session, cost) if calls["n"] == 1 else (real(self, session, cost) and False)
        return ok

    monkeypatch.setattr(runner.BudgetController, "can_spend", deny_second)

    class Spy(Provider):
        async def complete(self, request):
            seen.append(db.in_transaction())
            return await super().complete(request)

    cjk = good(thesis="El contrato \u4e2d\u6587\u6a21\u578b mejora la visibilidad de ingresos del trimestre.")
    with pytest.raises(ProposalRejected, match="presupuesto_agotado"):
        run(db, Spy(cjk, good()))
    assert seen == [False] and db.in_transaction() is False
