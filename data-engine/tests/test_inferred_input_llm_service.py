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
from app.models.entities import BudgetUsage, Company, Document, DocumentChunk, InferredInput
from app.services import inferred_input_llm_service as svc

NOW = datetime(2026, 10, 8, 12, tzinfo=UTC)
CHUNK = "El flujo de caja libre fue de 12 M USD sobre ingresos de 100 M USD; el margen FCF del ejercicio fue 12%."


def good(**over):
    base = {"value": 0.12, "source_ids": ["src:1"],
            "base": "Dado que el extracto src:1 indica FCF 12 M sobre ingresos 100 M, inferimos un margen FCF de 0.12."}
    base.update(over)
    return base


class Provider:
    name = "stub"

    def __init__(self, *outs):
        self.outs, self.calls, self.in_tx = list(outs), 0, []
        self.db = None

    async def complete(self, request):
        self.calls += 1
        if self.db is not None:
            self.in_tx.append(self.db.in_transaction())
        out = self.outs.pop(0)
        return LLMResponse(Message("assistant", out if isinstance(out, str) else json.dumps(out)),
                           Usage(10, 10, 20), "m", "p")


@pytest.fixture
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=True) as s:
        s.add_all([Tenant(id=1, external_id="i-1"), Tenant(id=2, external_id="i-2")])
        s.commit()
        s.info["tenant_id"] = 1
        s.add(Company(id=1, ticker="ASTS", name="AST", exchange="NASDAQ", company_type="pre_revenue",
                      valuation_model="pre_revenue"))
        s.add(Document(id=1, company_id=1, title="10-K", source_type="sec", published_at=NOW - timedelta(days=30),
                       source_url="https://www.sec.gov/Archives/edgar/data/1/10k.htm"))
        s.add(Document(id=2, company_id=1, title="Sin URL", source_type="note", source_url=None))
        s.add(DocumentChunk(document_id=1, chunk_index=0, text=CHUNK))
        s.add(DocumentChunk(document_id=2, chunk_index=0, text=CHUNK))
        s.commit()
        yield s
    engine.dispose()


def run(db, provider, ticker="ASTS"):
    provider.db = db
    return asyncio.run(svc.infer_fcf_margin(db, ticker, provider=provider, now=NOW))


def test_infers_from_ingested_sources_with_service_urls_and_label(db):
    row = run(db, Provider(good()))
    assert row.input_key == "fcf_margin" and row.origin == "llm" and float(row.value) == 0.12
    assert row.source_urls == ["https://www.sec.gov/Archives/edgar/data/1/10k.htm"]
    assert db.scalar(select(func.count(BudgetUsage.id)).where(BudgetUsage.workflow == "inferred_input")) == 1


def test_model_written_urls_are_ignored(db):
    row = run(db, Provider(good(base=good()["base"] + " Fuente: https://evil.example/x", urls=["https://evil.example/x"])))
    assert row.source_urls == ["https://www.sec.gov/Archives/edgar/data/1/10k.htm"]


def test_no_sources_is_nd_and_never_calls_the_model(db):
    db.query(DocumentChunk).delete()
    db.commit()
    p = Provider(good())
    with pytest.raises(svc.InferenceRejected, match="sin_fuentes"):
        run(db, p)
    assert p.calls == 0 and db.scalar(select(func.count(InferredInput.id))) == 0


@pytest.mark.parametrize("over,reason", [
    ({"source_ids": []}, "fuente_no_recibida"),
    ({"source_ids": ["src:2"]}, "fuente_no_recibida"),   # documento sin URL: no se entrego
    ({"source_ids": [{}]}, "fuente_no_recibida"),
    ({"base": "corta"}, "base_ausente"),
    ({"base": None}, "base_ausente"),
    ({"value": "NaN"}, "valor_fuera_de_rango"),
    ({"value": 0.9}, "valor_fuera_de_rango"),
    ({"value": True}, "valor_invalido"),
    ({"value": None}, "valor_invalido"),
])
def test_invalid_outputs_are_rejected_and_nothing_is_stored(db, over, reason):
    with pytest.raises(svc.InferenceRejected, match=reason):
        run(db, Provider(good(**over)))
    assert db.scalar(select(func.count(InferredInput.id))) == 0


def test_no_transaction_during_either_llm_call(db):
    cjk = good(base="Dado que el extracto \u4e2d\u6587\u6a21\u578b indica margen 12%, inferimos 0.12 de margen FCF.")
    p = Provider(cjk, good())
    row = run(db, p)
    assert row.id and p.in_tx == [False, False]


def test_daily_quota_blocks_before_calling_the_model(db):
    for i in range(svc.DAILY_QUOTA):
        db.add(InferredInput(tenant_id=1, company_id=1, input_key="fcf_margin", value=0.1,
                             base="b" * 25, source_urls=["https://a.example.com/x"], origin="llm",
                             created_at=NOW - timedelta(hours=1)))
    db.commit()
    p = Provider(good())
    with pytest.raises(svc.QuotaExceeded):
        run(db, p)
    assert p.calls == 0


def test_endpoint_statuses(db, monkeypatch):
    from app.api.routes.companies import router
    from app.core.database import get_db

    app = FastAPI()
    app.include_router(router, prefix="/companies")
    app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr(svc, "create_llm_provider", lambda: Provider(good()))
    client = TestClient(app)
    assert client.post("/companies/ZZZZ/inferred-inputs/llm", json={}).status_code == 404
    assert client.post("/companies/ASTS/inferred-inputs/llm", json={"input_key": "wacc"}).status_code == 422
    ok = client.post("/companies/ASTS/inferred-inputs/llm", json={})
    assert ok.status_code == 201, ok.text
    assert ok.json()["origin"] == "llm" and ok.json()["input_key"] == "fcf_margin"
