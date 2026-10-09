import asyncio
import importlib.util
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.routes.bottlenecks import router
from app.core.database import Base, get_db
from app.llm import LLMResponse, Message, Usage
from app.models import BottleneckDiscovery, BottleneckSignal, Company, NewsEvent, Tenant
from app.models.entities import BudgetUsage
from app.services import bottleneck_discovery_service as svc
from app.services.bottleneck_service import refresh_signals
from app.services.llm_router import ROUTES, route_model
from app.workers import dramatiq_app

NOW = datetime(2026, 10, 9, 10, tzinfo=UTC)
GOOD_REASON = "Fabrica obleas y podria beneficiarse de la restriccion de oferta descrita en las fuentes."


class Provider:
    name = "stub"

    def __init__(self, *outs):
        self.outs, self.calls = list(outs), 0

    async def complete(self, request):
        self.calls += 1
        out = self.outs.pop(0)
        text = out if isinstance(out, str) else json.dumps(out)
        return LLMResponse(Message("assistant", text), Usage(10, 10, 20), "space-bunny-free", "p")


def cand(ticker="NVDA", motivo=GOOD_REASON, ids=("news_event:1",)):
    return {"ticker": ticker, "motivo": motivo, "evidence_ids": list(ids)}


def out(*candidates):
    return {"candidatos": list(candidates)}


@pytest.fixture
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        session.add_all([Tenant(id=1, external_id="a"), Tenant(id=2, external_id="b")])
        session.commit()
        session.info["tenant_id"] = 1
        for i, ticker in enumerate(["NVDA", "AMD", "TSM"], start=1):
            session.add(Company(id=i, ticker=ticker, name=ticker, exchange="NASDAQ",
                                company_type="large_cap", valuation_model="dcf"))
        session.add_all([
            NewsEvent(id=1, title="Chip shortages persist", url="https://pub-a.example/n1",
                      date=datetime(2026, 10, 3, tzinfo=UTC)),
            NewsEvent(id=2, title="Escasez de chips durante el trimestre", url="https://pub-b.example/n2",
                      date=datetime(2026, 10, 4, tzinfo=UTC)),
            NewsEvent(id=3, title="Chip shortages worsen further", url=None,
                      date=datetime(2026, 10, 5, tzinfo=UTC)),
        ])
        session.commit()
        refresh_signals(session)
        session.commit()
        yield session
    engine.dispose()


def run(db, provider, **kw):
    kw.setdefault("now", NOW)
    return asyncio.run(svc.discover(db, provider=provider, **kw))


def stored(db):
    return list(db.scalars(select(BottleneckDiscovery)))


def test_route_is_free_and_registered():
    assert "bottleneck_discovery" in ROUTES
    assert route_model("bottleneck_discovery").task == "bottleneck_discovery"
    assert route_model("bottleneck_discovery").model in svc.VERIFIED_FREE_MODELS


def test_happy_path_saves_inferred_with_budget_record(db):
    provider = Provider(out(cand(ids=("news_event:1", "news_event:2"))))
    result = run(db, provider)
    assert result["status"] == "ok" and result["saved"] == 1 and result["themes_considered"] == 1
    row = stored(db)[0]
    assert (row.label, row.ticker, row.theme, row.model) == ("INFERIDO", "NVDA", "Semiconductores", "space-bunny-free")
    assert row.evidence_ids == ["news_event:1", "news_event:2"] and row.tenant_id == 1
    assert db.scalar(select(func.count(BudgetUsage.id)).where(BudgetUsage.workflow == "bottleneck_discovery")) == 1


def test_context_contains_only_evidence_texts(db):
    ctx = svc.load_theme_contexts(db)
    assert [c.theme for c in ctx] == ["Semiconductores"]
    assert {e.id for e in ctx[0].evidence} == {"news_event:1", "news_event:2", "news_event:3"}
    payload = json.loads(svc.build_request(ctx[0]).messages[1].content)
    assert set(payload) == {"tema", "evidencias"}
    assert all(set(e) == {"id", "texto"} for e in payload["evidencias"])


@pytest.mark.parametrize("item,reason", [
    (cand(ids=("news_event:99",)), "evidencia_no_recibida"),
    (cand(ids=("news_event:1", "document_chunk:1")), "evidencia_no_recibida"),
    (cand(ids=()), "sin_evidencia"),
    (cand(ticker="ZZZZ"), "ticker_inexistente"),
    (cand(ticker="nvda; DROP"), "ticker_invalido"),
    (cand(motivo="La empresa vale 150 dolares por accion segun las fuentes citadas."), "cifras_generadas"),
    (cand(motivo="Ingresos de cinco euros por unidad segun las fuentes citadas aqui."), "cifras_generadas"),
    (cand(motivo="Mas detalle en https://evil.example/x segun las fuentes citadas."), "url_generada"),
    (cand(motivo="Mas detalle en www.ejemplo.com segun las fuentes citadas por ellos."), "url_generada"),
    (cand(motivo="Short"), "motivo_invalido"),
])
def test_rejections_never_persist(db, item, reason):
    result = run(db, Provider(out(item)))
    assert result["saved"] == 0 and result["rejected"] == {reason: 1}
    assert stored(db) == []


@pytest.mark.parametrize("motivo", [
    "这家公司可能受益于芯片短缺的供应限制情况说明很长很长很长",
    "The company therefore may benefit however from the supply shortage here.",
])
def test_reasoning_guard_per_candidate(motivo):
    result = svc._check_candidate(cand(motivo=motivo), {"news_event:1"}, {"NVDA"})
    assert result == "motivo_rechazado_por_guard"


def test_guarded_output_rejected_twice_persists_nothing(db):
    bad = out(cand(motivo="这家公司可能受益于芯片短缺的供应限制情况说明很长很长很长"))
    result = run(db, Provider(bad, bad))
    assert result["rejected"] == {"salida_rechazada": 1} and stored(db) == []


def test_nd_ticker_allowed_and_duplicates_dropped(db):
    result = run(db, Provider(out(cand(ticker="N/D"), cand(ticker="NVDA"), cand(ticker="nvda"))))
    assert result["saved"] == 2 and result["rejected"] == {"ticker_duplicado": 1}
    assert {r.ticker for r in stored(db)} == {"N/D", "NVDA"}


def test_malformed_json_and_provider_error_degrade(db):
    assert run(db, Provider("no es json"))["errors"] == 1
    assert run(db, Provider({"otra": 1}))["rejected"] == {"json_invalido": 1}

    class Boom(Provider):
        async def complete(self, request):
            raise RuntimeError("provider down")

    result = run(db, Boom())
    assert result["status"] == "partial" and result["errors"] == 1 and stored(db) == []


def test_guard_retry_records_budget_for_each_call(db):
    bad = "这家公司可能受益于芯片短缺" * 4
    provider = Provider(out(cand(motivo=bad)), out(cand()))
    result = run(db, provider)
    assert provider.calls == 2 and result["saved"] == 1
    assert db.scalar(select(func.count(BudgetUsage.id))) == 2


def test_daily_quota(db, monkeypatch):
    monkeypatch.setattr(svc, "DAILY_QUOTA", 1)
    result = run(db, Provider(out(cand(ticker="NVDA"), cand(ticker="AMD"))))
    assert result["saved"] == 1 and len(stored(db)) == 1
    provider = Provider(out(cand(ticker="TSM")))
    again = run(db, provider)
    assert again["status"] == "skipped" and again["stop_reason"] == "cuota_agotada"
    assert provider.calls == 0 and len(stored(db)) == 1


def test_quota_exhausted_mid_run_is_partial(db, monkeypatch):
    db.add(BottleneckDiscovery(theme="Energía", ticker="AMD", reasoning="x", evidence_ids=[], model="m",
                               day=NOW.date(), created_at=NOW))
    db.commit()
    monkeypatch.setattr(svc, "DAILY_QUOTA", 2)
    run(db, Provider(out(cand(ticker="NVDA"))))
    assert len(stored(db)) == 2
    real = svc.todays_discoveries
    first = []

    def blind_once(d, n):  # el pre-chequeo no ve la cuota llena; el guardado bajo candado si
        if not first:
            first.append(1)
            return 0
        return real(d, n)

    monkeypatch.setattr(svc, "todays_discoveries", blind_once)
    result = run(db, Provider(out(cand(ticker="TSM"))))
    assert result["status"] == "partial" and result["stop_reason"] == "cuota_agotada"


def test_same_day_rerun_is_idempotent(db):
    run(db, Provider(out(cand())))
    result = run(db, Provider(out(cand())))
    assert result["saved"] == 0 and len(stored(db)) == 1


def test_budget_exceeded_stops_before_calling_model(db, monkeypatch):
    monkeypatch.setattr(svc.BudgetController, "can_spend", lambda self, d, c: False)
    provider = Provider(out(cand()))
    result = run(db, provider)
    assert result["status"] == "partial" and result["stop_reason"] == "presupuesto_agotado"
    assert provider.calls == 0 and stored(db) == []


def test_budget_exhausted_before_guard_retry(db, monkeypatch):
    answers = iter([True, False])
    monkeypatch.setattr(svc.BudgetController, "can_spend", lambda self, d, c: next(answers))
    provider = Provider(out(cand(motivo="这家公司可能受益于芯片短缺" * 4)), out(cand()))
    result = run(db, provider)
    assert result["stop_reason"] == "presupuesto_agotado" and provider.calls == 1 and stored(db) == []


def test_disabled_and_non_free_route_skip(db, monkeypatch):
    class Off(Provider):
        name = "disabled"

    assert run(db, Off())["stop_reason"] == "llm_deshabilitado"
    monkeypatch.setattr(svc, "route_model", lambda task: type("R", (), {"model": "caro-pro"})())
    provider = Provider(out(cand()))
    assert run(db, provider)["stop_reason"] == "modelo_no_gratuito" and provider.calls == 0


def test_session_released_before_llm_call(db):
    seen = []

    class Watcher(Provider):
        async def complete(self, request):
            seen.append(db.in_transaction())
            return await super().complete(request)

    run(db, Watcher(out(cand())))
    assert seen == [False]


def test_min_sources_threshold(db):
    assert run(db, Provider(), min_sources=3)["themes_considered"] == 0
    row = db.scalar(select(BottleneckSignal))
    row.n_sources = 1
    db.commit()
    assert svc.load_theme_contexts(db) == []


def test_tenant_isolation(db):
    run(db, Provider(out(cand())))
    db.info["tenant_id"] = 2
    # señal forjada del tenant 2 que apunta a ids del tenant 1: no se resuelven
    db.add(BottleneckSignal(theme="Semiconductores", evidence_ids=["news_event:1", "news_event:2"], n_sources=5))
    db.commit()
    assert svc.resolve_evidence(db, ["news_event:1"]) == {}
    provider = Provider(out(cand()))
    result = run(db, provider)
    assert result["themes_considered"] == 0 and provider.calls == 0
    assert stored(db) == []
    app = FastAPI()
    app.include_router(router, prefix="/api/bottlenecks")
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        body = client.get("/api/bottlenecks/discoveries").json()
    assert body["items"] == [] and body["total"] == 0
    db.info.clear()
    assert svc.load_theme_contexts(db) == [] and svc.resolve_evidence(db, ["news_event:1"]) == {}


def test_e2e_to_endpoint_with_real_urls_and_pagination(db):
    run(db, Provider(out(cand(ticker="NVDA", ids=("news_event:1", "news_event:3")), cand(ticker="AMD"))))
    app = FastAPI()
    app.include_router(router, prefix="/api/bottlenecks")
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        body = client.get("/api/bottlenecks/discoveries").json()
        assert body["total"] == 2 and body["has_more"] is False and "INFERIDO" in body["note"]
        nvda = next(i for i in body["items"] if i["ticker"] == "NVDA")
        assert nvda["label"] == "INFERIDO" and nvda["reasoning"] == GOOD_REASON
        assert nvda["evidence"][0] == {"id": "news_event:1", "title": "Chip shortages persist",
                                       "url": "https://pub-a.example/n1", "status": "verificada"}
        assert nvda["evidence"][1]["url"] is None and nvda["evidence"][1]["status"] == "N/D"
        page = client.get("/api/bottlenecks/discoveries", params={"limit": 1, "offset": 0}).json()
        assert len(page["items"]) == 1 and page["has_more"] is True
        assert client.get("/api/bottlenecks/discoveries", params={"limit": 1, "offset": 1}).json()["has_more"] is False
        assert client.get("/api/bottlenecks/discoveries", params={"limit": 0}).status_code == 422
        assert client.get("/api/bottlenecks/discoveries", params={"limit": 101}).status_code == 422
        assert client.get("/api/bottlenecks").status_code == 200  # la ruta antigua sigue igual


def test_endpoint_without_tenant_is_empty(db):
    db.info.clear()
    app = FastAPI()
    app.include_router(router, prefix="/api/bottlenecks")
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        assert client.get("/api/bottlenecks/discoveries").json()["items"] == []


def test_non_http_urls_are_nd():
    assert svc._real_url("javascript:alert(1)") is None
    assert svc._real_url("  https://ok.example/a ") == "https://ok.example/a"
    assert svc._real_url(None) is None


def test_label_is_enforced_by_schema(db):
    from sqlalchemy.exc import IntegrityError

    db.add(BottleneckDiscovery(theme="t", ticker="X", reasoning="r", evidence_ids=[], model="m", label="HECHO",
                               day=NOW.date(), created_at=NOW))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_migration_upgrade_downgrade():
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect

    path = Path(__file__).parents[1] / "alembic/versions/0057_bottleneck_discovery.py"
    spec = importlib.util.spec_from_file_location("migration_discovery", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.down_revision == "0056_bottleneck_signal"
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        module.op = Operations(MigrationContext.configure(conn))
        module.upgrade()
        columns = {c["name"] for c in inspect(conn).get_columns("bottleneck_discovery")}
        assert columns == {c.name for c in BottleneckDiscovery.__table__.columns}
        module.downgrade()
        assert "bottleneck_discovery" not in inspect(conn).get_table_names()
    engine.dispose()


# --- actor ------------------------------------------------------------------

def _fn() -> Callable[..., dict[str, Any]]:
    return cast(Callable[..., dict[str, Any]], getattr(dramatiq_app.discover_bottlenecks, "fn", dramatiq_app.discover_bottlenecks))


@pytest.fixture
def actor_env(db, monkeypatch):
    monkeypatch.setattr(db, "close", lambda: None)
    monkeypatch.setattr(dramatiq_app, "_session", lambda t, u: db)
    monkeypatch.setattr(dramatiq_app, "_run", lambda coro: asyncio.run(coro))
    monkeypatch.setattr(svc, "create_llm_provider", lambda: Provider(out(cand())))
    return db


class FakeDeadline:
    def __init__(self, expired_value=False, truncated=False):
        self._expired, self.truncated = expired_value, truncated

    def expired(self):
        return self._expired


def test_actor_declares_explicit_time_limit():
    options = dramatiq_app.discover_bottlenecks.options
    assert options["time_limit"] == 600_000 and options["max_retries"] == 1
    assert options["time_limit"] > dramatiq_app.DISCOVERY_DEADLINE_SECONDS * 1000


def test_actor_ok(actor_env):
    result = _fn()(1, "u")
    assert result["actor"] == "discover_bottlenecks" and result["status"] == "ok" and result["saved"] == 1


def test_actor_returns_partial_when_deadline_truncates(actor_env, monkeypatch):
    monkeypatch.setattr("app.services.ticker_news_lane.Deadline", lambda s: FakeDeadline(expired_value=True))
    result = _fn()(1, "u")
    assert result["status"] == "partial" and result["stop_reason"] == "deadline" and result["saved"] == 0


def test_actor_marks_truncated_sweep_partial_even_if_loop_finished(actor_env, monkeypatch):
    monkeypatch.setattr("app.services.ticker_news_lane.Deadline", lambda s: FakeDeadline(truncated=True))
    assert _fn()(1, "u")["status"] == "partial"


def test_actor_skipped_when_llm_disabled(actor_env, monkeypatch):
    class Off(Provider):
        name = "disabled"

    monkeypatch.setattr(svc, "create_llm_provider", lambda: Off())
    result = _fn()(1, "u")
    assert result["status"] == "skipped" and result["stop_reason"] == "llm_deshabilitado"


def test_actor_permanent_error_is_structured_and_transient_retries(actor_env, monkeypatch):
    async def boom(db, **kw):
        raise ValueError("permanente")

    monkeypatch.setattr(svc, "discover", boom)
    assert _fn()(1, "u")["status"] == "error"

    async def transient(db, **kw):
        raise ConnectionError("db down")

    monkeypatch.setattr(svc, "discover", transient)
    with pytest.raises(ConnectionError):
        _fn()(1, "u")


def test_resolves_document_and_knowledge_lanes_with_real_urls(db):
    from datetime import date

    from app.models import Document, DocumentChunk, KnowledgeChunk, KnowledgeDocument

    doc = Document(title="Filing", source_type="filing", source_url="https://chips.example/filing",
                   published_at=datetime(2026, 10, 1, tzinfo=UTC))
    letter = KnowledgeDocument(title="Carta", document_type="fund_letter", author="Fondo A",
                               source_url="ftp://no-http.example/x", publication_date=date(2026, 10, 2),
                               status="ready")
    db.add_all([doc, letter])
    db.flush()
    dchunk = DocumentChunk(document_id=doc.id, chunk_index=0, text="Chip shortages persist")
    kchunk = KnowledgeChunk(knowledge_document_id=letter.id, chunk_index=0, content="Escasez de chips")
    db.add_all([dchunk, kchunk])
    db.commit()
    ids = [f"document_chunk:{dchunk.id}", f"knowledge_chunk:{kchunk.id}", "news_event:abc", "otro:1"]
    found = svc.resolve_evidence(db, ids)
    assert set(found) == set(ids[:2])
    assert found[ids[0]].url == "https://chips.example/filing" and found[ids[0]].title == "Filing"
    assert found[ids[1]].url is None and found[ids[1]].text == "Escasez de chips"
    db.info["tenant_id"] = 2
    assert svc.resolve_evidence(db, ids) == {}
