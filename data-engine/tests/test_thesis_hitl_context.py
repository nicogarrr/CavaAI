"""Human inputs are explicit, atomic and isolated; retrieval cannot forge citations."""
from decimal import Decimal

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api.routes.thesis import ThesisInputsRequest, submit_thesis_inputs
from app.models import (
    Company,
    Document,
    DocumentChunk,
    DriverAssumptionVersion,
    FundamentalDriver,
    FundamentalModelVersion,
    Tenant,
)
from app.models.entities import Base
from app.services import thesis_context
from app.services.thesis_narrative_llm import (
    _fragment_templates,
    _section_templates,
    _validated_section_selection,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        tenant = Tenant(external_id="hitl-test", name="test")
        db.add(tenant)
        db.flush()
        db.info["tenant_id"] = tenant.id
        company = Company(ticker="ASTS", name="AST SpaceMobile", exchange="NASDAQ", currency="USD", sector="Telecom", industry="Satellites", company_type="growth", valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[])
        db.add(company)
        db.flush()
        model = FundamentalModelVersion(company_id=company.id, version=1, engine_version="test", algorithm_version="test", framework_key="generic_fcf", horizon_years=5, status="ok", publishable=False, input_fingerprint="a"*64, forecast_fingerprint="b"*64, market_snapshot_fingerprint="c"*64, valuation_snapshot_fingerprint="d"*64)
        db.add(model)
        db.flush()
        db.add(FundamentalDriver(model_version_id=model.id, company_id=company.id, driver_key="revenue", driver_type="revenue_driver", status="pending", value=None))
        db.commit()
        yield db, company


def payload(key="revenue", value="50"):
    return {"driver_key": key, "fiscal_year": 2027, "scenario": "base", "value": value, "source": "human plan", "rationale": "Explicit assumption, not reported data"}


def test_human_input_versions_and_forces_assumption(db):
    session, _ = db
    request = ThesisInputsRequest(inputs=[payload()])
    first = submit_thesis_inputs("ASTS", request, session)
    second = submit_thesis_inputs("ASTS", request, session)
    assert first["provenance_label"] == "supuesto"
    assert first["requires_regeneration"] is True
    assert second["inputs"][0]["previous_version_id"] == first["inputs"][0]["id"]
    version = session.scalar(select(DriverAssumptionVersion).order_by(DriverAssumptionVersion.id))
    assert version.user_override is True
    assert version.value == Decimal("50")


def test_bad_second_input_rolls_back_entire_batch(db):
    session, _ = db
    request = ThesisInputsRequest(inputs=[payload(), payload("not_a_driver")])
    with pytest.raises(HTTPException) as error:
        submit_thesis_inputs("ASTS", request, session)
    assert error.value.status_code == 409
    assert session.query(DriverAssumptionVersion).count() == 0


def test_nonfinite_and_empty_inputs_rejected():
    for bad in ([], [payload(value="NaN")], [payload(value="Infinity")]):
        with pytest.raises(ValidationError):
            ThesisInputsRequest(inputs=bad)


def test_no_tenant_cannot_submit(db):
    session, _ = db
    session.info.pop("tenant_id")
    with pytest.raises(HTTPException) as error:
        submit_thesis_inputs("ASTS", ThesisInputsRequest(inputs=[payload()]), session)
    assert error.value.status_code == 403


def test_retrieval_checks_postgres_and_never_trusts_vector_payload(db, monkeypatch):
    session, company = db
    doc = Document(company_id=company.id, title="Actual filing", source_type="sec_filing", source_url="https://example.org/filing")
    session.add(doc)
    session.flush()
    chunk = DocumentChunk(document_id=doc.id, chunk_index=0, text="Actual excerpt")
    session.add(chunk)
    session.commit()
    calls = []
    def search(self, query, **kwargs):
        calls.append(kwargs)
        return [
            {"entity_type": "document_chunk", "entity_id": chunk.id, "text": "forged text", "url": "https://evil.invalid"},
            {"entity_type": "document_chunk", "entity_id": chunk.id},
            {"entity_type": "document_chunk", "entity_id": 99999},
            {"entity_type": "knowledge_chunk", "entity_id": chunk.id},
        ]
    monkeypatch.setattr(thesis_context.RAGIndex, "search", search)
    context = thesis_context.retrieve_thesis_context(session, company)
    assert len(context) == 1
    assert context[0]["text"] == "Actual excerpt"
    assert context[0]["url"] == doc.source_url
    assert calls[0]["tenant_id"] == session.info["tenant_id"]
    assert calls[0]["ticker"] == "ASTS"
    # Explicit predicates guard both another tenant and another company.
    other = Company(ticker="OTHER", name="Other", exchange="NASDAQ", currency="USD", sector="", industry="", company_type="growth", valuation_model="unassigned")
    session.add(other)
    session.commit()
    assert thesis_context.retrieve_thesis_context(session, other) == []
    session.info["tenant_id"] = 999
    assert thesis_context.retrieve_thesis_context(session, company) == []


def test_rag_failure_and_no_tenant_are_honest_empty(db, monkeypatch):
    session, company = db
    def search(*args, **kwargs):
        raise RuntimeError("Qdrant unavailable")
    monkeypatch.setattr(thesis_context.RAGIndex, "search", search)
    assert thesis_context.retrieve_thesis_context(session, company) == []
    session.info.pop("tenant_id")
    assert thesis_context.retrieve_thesis_context(session, company) == []


def test_insufficient_thesis_includes_news_but_no_unreliable_value(db):
    _, company = db
    valuation = {"status": "insufficient_data", "missing_inputs": ["revenue"], "current_price": 1, "base_value": 2, "margin_of_safety": 1}
    news = [{"source_headline": "Launch announced", "source": "Agency", "url": "https://example.org/news"}]
    fragments = _fragment_templates(company, valuation, news)
    assert "titular_0" in fragments
    assert "https://example.org/news" in fragments["titular_0"]
    assert "valoracion_posicion" not in fragments
    sections = _section_templates(company, valuation, None, news, [{"form": "8-K", "url": "https://example.org/8k"}], [])
    assert "Sin contexto RAG" in sections["contexto_rag"]["parrafos"][0]
    assert _validated_section_selection(["lo_que_sabemos", "no_sabemos"], sections) is None
    selected = _validated_section_selection(["lo_que_sabemos", "lo_que_cambio", "filings", "contexto_rag", "no_sabemos"], sections)
    assert selected is not None
    assert "https://example.org/8k" in selected[2]["parrafos"][0]


def test_http_inputs_contract(db):
    from fastapi import FastAPI

    from app.api.routes.thesis import router
    from app.core.database import get_db

    session, _ = db
    application = FastAPI()
    application.include_router(router, prefix="/thesis")
    application.dependency_overrides[get_db] = lambda: session
    spec = application.openapi()
    operation = spec["paths"]["/thesis/{ticker}/inputs"]["post"]
    assert "201" in operation["responses"]
    assert operation["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith("/ThesisInputsRequest")
    assert spec["components"]["schemas"]["ThesisInputsRequest"]["properties"]["inputs"]["maxItems"] == 30
