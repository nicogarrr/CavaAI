import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.llm import LLMResponse, Message, Usage
from app.llm.errors import ProviderResponseError, ProviderTransportError
from app.models import Tenant
from app.models.entities import BudgetUsage, Company, NewsEvent
from app.models.paper_trading import PaperTrade
from app.services import llm_proposal_runner as runner
from app.services import llm_proposal_service as proposal_service
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


class FreeRouter:
    """Router del adaptador real: resuelve el modelo que se usaria de verdad."""

    def __init__(self, resolved=None):
        self.resolved = resolved

    def resolve(self, request):
        return self.resolved or request.model or "space-bunny-free"


class Provider:
    name = "stub"
    _fallback_model: Any = None

    def __init__(self, *outs):
        self.outs, self.calls = list(outs), 0
        self.model_router: Any = FreeRouter()

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


def test_quota_is_atomic_under_concurrent_saves(tmp_path):
    import threading

    from app.schemas.paper_trading import PaperProposal

    engine = create_engine(f"sqlite:///{tmp_path / 'q.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add_all([Tenant(id=1, external_id="q-1"), Tenant(id=2, external_id="q-2")])
        s.commit()

    def make(i, tenant=1):
        return PaperProposal(
            proposal_key=f"llm:AAPL:20261008:{tenant}{i}", ticker="AAPL", direction="long", horizon="short",
            thesis="El contrato nuevo mejora la visibilidad de ingresos del trimestre.", conviction=0.5,
            proposed_entry=99, stop=92, target=115, quantity=10,
            inference_basis="Inferencia propia sobre el titular.", currency="USD",
        )

    def save(i, tenant, out):
        with Session(engine, expire_on_commit=False) as s:
            s.info["tenant_id"] = tenant
            try:
                runner.save_within_quota(s, make(i, tenant), NOW)
                out.append("ok")
            except runner.QuotaExceeded:
                out.append("quota")

    first = []
    for i in range(runner.DAILY_QUOTA - 1):
        save(i, 1, first)
    assert first == ["ok"] * (runner.DAILY_QUOTA - 1)
    out = []
    threads = [threading.Thread(target=save, args=(100 + i, 1, out)) for i in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(out) == ["ok"] + ["quota"] * 5
    other = []
    save(0, 2, other)  # otro tenant no comparte cuota
    assert other == ["ok"]
    with Session(engine) as s:
        s.info["tenant_id"] = 1
        assert runner.todays_llm_proposals(s, NOW) == runner.DAILY_QUOTA
    engine.dispose()


def test_retry_budget_denial_keeps_first_cost_and_endpoint_returns_503(db, monkeypatch):
    from app.api.routes.paper_trading import router
    from app.core.database import get_db

    n = {"i": 0}
    real = runner.BudgetController.can_spend

    def deny_retry(self, session, cost):
        n["i"] += 1
        return real(self, session, cost) if n["i"] == 1 else False

    monkeypatch.setattr(runner.BudgetController, "can_spend", deny_retry)
    cjk = good(thesis="El contrato \u4e2d\u6587\u6a21\u578b mejora la visibilidad de ingresos del trimestre.")
    provider = Provider(cjk, good())
    app = FastAPI()
    app.include_router(router, prefix="/paper-trading")
    app.dependency_overrides[get_db] = lambda: db
    db.get(NewsEvent, 1).date = datetime.now(UTC) - timedelta(days=1)
    db.commit()
    monkeypatch.setattr(runner, "create_llm_provider", lambda: provider)
    monkeypatch.setattr(
        "app.api.routes.market.market_quote",
        lambda t: {"live_c": 100.0, "live_t": datetime.now(UTC).timestamp() - 60, "currency": "USD"},
    )
    res = TestClient(app).post("/paper-trading/llm-proposals", json={"ticker": "AAPL"})
    assert res.status_code == 503 and "presupuesto_agotado" in res.text
    assert provider.calls == 1
    assert db.scalar(select(func.count(BudgetUsage.id)).where(BudgetUsage.workflow == "llm_proposal")) == 1
    assert db.scalar(select(func.count(PaperTrade.id))) == 0


def test_paid_or_unverifiable_model_blocks_before_any_spend(db):
    paid = Provider(good())
    paid.model_router = FreeRouter("gpt-paid-model")
    with pytest.raises(ProposalRejected) as exc:
        run(db, paid)
    assert exc.value.reason == "modelo_no_gratuito" and paid.calls == 0

    paid_fallback = Provider(good())
    paid_fallback._fallback_model = "gpt-paid-model"
    with pytest.raises(ProposalRejected) as exc:
        run(db, paid_fallback)
    assert exc.value.reason == "fallback_no_gratuito" and paid_fallback.calls == 0

    blind = Provider(good())
    blind.model_router = None
    with pytest.raises(ProposalRejected) as exc:
        run(db, blind)
    assert exc.value.reason == "modelo_no_verificable" and blind.calls == 0


def test_future_dated_news_is_not_given_to_the_model(db):
    db.add(NewsEvent(id=2, company_id=1, date=NOW + timedelta(days=1), title="Titular futuro", source="X"))
    db.commit()
    titles = [h["title"] for h in runner.load_headlines(db, "AAPL", NOW)]
    assert "Titular futuro" not in titles and titles


def test_guard_probe_is_the_real_request_not_a_pinned_model(db):
    """Un override por tarea solo se ve si la sonda no fija modelo, como la peticion real."""

    class TaskOverrideRouter:
        def resolve(self, request):
            if request.model is None and request.task == "main_financial_analysis":
                return "paid-model"  # override de entorno por tarea
            return request.model or "space-bunny-free"

    provider = Provider(good())
    provider.model_router = TaskOverrideRouter()
    with pytest.raises(ProposalRejected) as exc:
        run(db, provider)
    assert exc.value.reason == "modelo_no_gratuito" and provider.calls == 0


def test_quote_received_after_start_is_fresh_against_the_post_fetch_clock(db):
    ticks = iter([NOW, NOW + timedelta(seconds=5), NOW + timedelta(seconds=5)])

    def late_quote(ticker):
        # la cotizacion llega 2 s DESPUES del arranque: futura para un reloj congelado
        return {"live_c": 100.0, "live_t": (NOW + timedelta(seconds=2)).timestamp(), "currency": "USD"}

    row = asyncio.run(runner.generate_proposal(
        db, "AAPL", provider=Provider(good()), fetch_quote=late_quote, clock=lambda: next(ticks),
    ))
    assert row.ticker == "AAPL"


def test_quote_from_the_future_is_still_rejected_with_a_frozen_clock(db):
    def late_quote(ticker):
        return {"live_c": 100.0, "live_t": (NOW + timedelta(seconds=2)).timestamp(), "currency": "USD"}

    with pytest.raises(ProposalRejected):
        asyncio.run(runner.generate_proposal(
            db, "AAPL", provider=Provider(good()), fetch_quote=late_quote, now=NOW,
        ))


class Flaky(Provider):
    """Falla con los errores indicados y luego responde segun `outs`."""

    def __init__(self, errors, *outs):
        super().__init__(*outs)
        self.errors, self.attempts = list(errors), 0

    async def complete(self, request):
        self.attempts += 1
        if self.errors:
            raise self.errors.pop(0)
        return await super().complete(request)


@pytest.fixture
def fast_retry(monkeypatch):
    monkeypatch.setattr(proposal_service, "TRANSIENT_RETRY_PAUSE", 0)


def test_empty_reply_is_retried_once_and_succeeds(db, fast_retry):
    provider = Flaky([ProviderResponseError("opencode-go returned an empty assistant message")], good())
    row = run(db, provider)
    assert row.ticker == "AAPL" and provider.attempts == 2


def test_timeout_is_retried_once_then_gives_up(db, fast_retry):
    errors = [ProviderTransportError("opencode-go", "timeout", 1), ProviderTransportError("opencode-go", "timeout", 1)]
    provider = Flaky(errors, good())
    with pytest.raises(ProviderTransportError):
        run(db, provider)
    assert provider.attempts == 2  # una sola vez, nunca un bucle


def test_non_transient_errors_are_not_retried(db, fast_retry):
    provider = Flaky([ProviderResponseError("opencode-go returned a malformed tool call")], good())
    with pytest.raises(ProviderResponseError):
        run(db, provider)
    assert provider.attempts == 1
    provider = Flaky([ProviderTransportError("opencode-go", "connect_error", 1)], good())
    with pytest.raises(ProviderTransportError):
        run(db, provider)
    assert provider.attempts == 1


def test_retry_is_blocked_when_budget_is_exhausted_and_session_is_released(db, fast_retry, monkeypatch):
    from app.services.budget import BudgetController

    answers = iter([True, False])  # el primer chequeo pasa; el previo al reintento no
    monkeypatch.setattr(BudgetController, "can_spend", lambda self, db, amount: next(answers))
    provider = Flaky([ProviderResponseError("opencode-go returned no assistant message")], good())
    with pytest.raises(ProposalRejected) as exc:
        run(db, provider)
    assert exc.value.reason == "presupuesto_agotado" and provider.attempts == 1


def test_transport_retry_does_not_reset_the_single_output_retry(db, fast_retry):
    """CJK -> timeout -> CJK: el limite de salida NO se resetea (sin 4a llamada)."""
    cjk = good(thesis="El contrato \u4e2d\u6587\u6a21\u578b mejora la visibilidad de ingresos del trimestre.")

    class Mixed(Provider):
        def __init__(self):
            super().__init__(cjk, cjk, good())
            self.n = 0

        async def complete(self, request):
            self.n += 1
            if self.n == 2:
                raise ProviderTransportError("opencode-go", "read_timeout", 1)
            return await super().complete(request)

    provider = Mixed()
    with pytest.raises(ProposalRejected) as exc:
        run(db, provider)
    # 1 CJK, 2 timeout (reintento transitorio), 3 CJK: el guard ya gasto su unico reintento
    # de salida, no hay 4a llamada y la propuesta valida (good) nunca se alcanza
    assert exc.value.reason == "salida_rechazada:cjk"
    assert provider.n == 3 and len(provider.outs) == 1
