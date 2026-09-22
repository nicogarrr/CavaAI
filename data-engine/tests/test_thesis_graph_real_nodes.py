"""Stage 6d/6e: real deterministic nodes (resolve_company, freeze_input_snapshot, probes)."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, Company
from app.workflows.thesis_graph import build_thesis_graph
from app.workflows.thesis_graph.checkpointer import sqlite_checkpointer


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _company(db: Session) -> Company:
    company = Company(
        ticker="AAPL", name="Apple", exchange="NASDAQ", currency="USD",
        sector="Tech", industry="Tech", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


class _Scope:
    def __init__(self, db):
        self._db = db

    def __call__(self):
        return self

    def __enter__(self):
        return self._db

    def __exit__(self, *args):
        return False


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def test_resolve_company_real_with_session_factory(db):
    company = _company(db)
    with sqlite_checkpointer() as saver:
        graph = build_thesis_graph(checkpointer=saver, session_factory=_Scope(db))
        graph.invoke({"ticker": "AAPL", "tenant_id": "t1"}, config=_config("t:r1"))
        state = graph.get_state(_config("t:r1")).values
    assert state["company_id"] == str(company.id)
    assert state["artifacts"]["resolve_company"] == f"company:{company.id}"


def test_resolve_company_unknown_ticker_fails_loudly(db):
    with sqlite_checkpointer() as saver:
        graph = build_thesis_graph(checkpointer=saver, session_factory=_Scope(db))
        with pytest.raises(ValueError, match="unknown_company:NOPE"):
            graph.invoke({"ticker": "NOPE", "tenant_id": "t1"}, config=_config("t:r2"))


def test_resolve_company_skeleton_without_session_factory():
    with sqlite_checkpointer() as saver:
        graph = build_thesis_graph(checkpointer=saver)
        graph.invoke({"ticker": "AAPL", "tenant_id": "t1"}, config=_config("t:r3"))
        state = graph.get_state(_config("t:r3")).values
    assert state["artifacts"]["resolve_company"] == "pending:resolve_company"
    assert "company_id" not in state


def test_freeze_input_snapshot_deterministic_and_idempotent(db):
    _company(db)
    with sqlite_checkpointer() as saver:
        graph = build_thesis_graph(checkpointer=saver, session_factory=_Scope(db))
        graph.invoke({"ticker": "AAPL", "tenant_id": "t1"}, config=_config("t:r4"))
        first = graph.get_state(_config("t:r4")).values
        # duplicate delivery: no new fingerprint, artifact unchanged
        graph.invoke({"ticker": "AAPL", "tenant_id": "t1"}, config=_config("t:r4"))
        second = graph.get_state(_config("t:r4")).values
    ref = first["artifacts"]["freeze_input_snapshot"]
    assert ref.startswith("sha256:") and len(ref) == len("sha256:") + 16
    assert first["input_fingerprint"] == ref.removeprefix("sha256:")
    assert second["artifacts"]["freeze_input_snapshot"] == ref


def test_caller_fingerprint_wins(db):
    _company(db)
    with sqlite_checkpointer() as saver:
        graph = build_thesis_graph(checkpointer=saver, session_factory=_Scope(db))
        graph.invoke(
            {"ticker": "AAPL", "tenant_id": "t1", "input_fingerprint": "caller-fp"},
            config=_config("t:r5"),
        )
        state = graph.get_state(_config("t:r5")).values
    assert state["input_fingerprint"] == "caller-fp"
    assert state["artifacts"]["freeze_input_snapshot"].startswith("sha256:")


# --- ensure_ingestion_complete: evidence coverage probe ---

def _seed_evidence(db: Session, company_id: int) -> None:
    from datetime import date

    from app.models import Document, FinancialFact, MarketPrice

    db.add(FinancialFact(
        company_id=company_id, metric="revenue", fiscal_year=2025, value=100,
        unit="USD", period="FY", source_type="test",
    ))
    db.add(MarketPrice(company_id=company_id, date=date(2026, 1, 2), close=200))
    db.add(Document(company_id=company_id, title="10-K", source_type="sec_filing"))
    db.commit()


def test_ingestion_probe_counts_evidence(db):
    company = _company(db)
    _seed_evidence(db, company.id)
    with sqlite_checkpointer() as saver:
        graph = build_thesis_graph(checkpointer=saver, session_factory=_Scope(db))
        graph.invoke({"ticker": "AAPL", "tenant_id": "t1"}, config=_config("t:i1"))
        state = graph.get_state(_config("t:i1")).values
    assert state["artifacts"]["ensure_ingestion_complete"] == "evidence:facts=1,prices=1,docs=1"
    assert state["meta"]["evidence_coverage"] == {
        "financial_facts": 1,
        "market_prices": 1,
        "documents": 1,
    }


def test_ingestion_probe_zero_coverage_is_honest_not_error(db):
    _company(db)
    with sqlite_checkpointer() as saver:
        graph = build_thesis_graph(checkpointer=saver, session_factory=_Scope(db))
        graph.invoke({"ticker": "AAPL", "tenant_id": "t1"}, config=_config("t:i2"))
        state = graph.get_state(_config("t:i2")).values
    assert state["artifacts"]["ensure_ingestion_complete"] == "evidence:facts=0,prices=0,docs=0"
    assert state["meta"]["evidence_coverage"] == {
        "financial_facts": 0,
        "market_prices": 0,
        "documents": 0,
    }


def test_ingestion_probe_skeleton_without_session_factory():
    with sqlite_checkpointer() as saver:
        graph = build_thesis_graph(checkpointer=saver)
        graph.invoke({"ticker": "AAPL", "tenant_id": "t1"}, config=_config("t:i3"))
        state = graph.get_state(_config("t:i3")).values
    assert state["artifacts"]["ensure_ingestion_complete"] == "pending:ensure_ingestion_complete"

# --- build_fundamental_model / deterministic_valuation: read-side probes ---

def _seed_model_and_valuation(db: Session, company_id: int) -> None:
    from app.models.entities import FundamentalModelVersion, FundamentalValuationSnapshot

    model = FundamentalModelVersion(
        company_id=company_id, version=3, engine_version="e1", algorithm_version="a1",
        framework_key="quality_compounder", horizon_years=5, status="final",
        publishable=True, input_fingerprint="fp-input-0123456789",
        forecast_fingerprint="fp-forecast", market_snapshot_fingerprint="fp-market",
        valuation_snapshot_fingerprint="fp-valuation", scenario_probabilities={},
        model_snapshot={},
    )
    db.add(model)
    db.flush()
    db.add(FundamentalValuationSnapshot(
        model_version_id=model.id, company_id=company_id, current_price=200,
        market_snapshot_fingerprint="fp-market",
        valuation_snapshot_fingerprint="fp-valuation-0123", snapshot={},
    ))
    db.commit()


def test_fundamental_model_probe_reads_latest(db):
    company = _company(db)
    _seed_model_and_valuation(db, company.id)
    with sqlite_checkpointer() as saver:
        graph = build_thesis_graph(checkpointer=saver, session_factory=_Scope(db))
        graph.invoke({"ticker": "AAPL", "tenant_id": "t1"}, config=_config("t:m1"))
        state = graph.get_state(_config("t:m1")).values
    assert state["artifacts"]["build_fundamental_model"] == "model:v3:fp-input-012"
    assert state["meta"]["fundamental_model"] == {
        "version": 3,
        "status": "final",
        "publishable": True,
        "framework_key": "quality_compounder",
    }
    assert state["artifacts"]["deterministic_valuation"] == "valuation:1"
    assert state["meta"]["valuation_snapshot"]["current_price"] == 200.0


def test_model_and_valuation_probes_honest_none(db):
    _company(db)
    with sqlite_checkpointer() as saver:
        graph = build_thesis_graph(checkpointer=saver, session_factory=_Scope(db))
        graph.invoke({"ticker": "AAPL", "tenant_id": "t1"}, config=_config("t:m2"))
        state = graph.get_state(_config("t:m2")).values
    assert state["artifacts"]["build_fundamental_model"] == "model:none"
    assert state["meta"]["fundamental_model"] is None
    assert state["artifacts"]["deterministic_valuation"] == "valuation:none"
    assert state["meta"]["valuation_snapshot"] is None


def test_model_and_valuation_probes_skeleton_without_session_factory():
    with sqlite_checkpointer() as saver:
        graph = build_thesis_graph(checkpointer=saver)
        graph.invoke({"ticker": "AAPL", "tenant_id": "t1"}, config=_config("t:m3"))
        state = graph.get_state(_config("t:m3")).values
    assert state["artifacts"]["build_fundamental_model"] == "pending:build_fundamental_model"
    assert state["artifacts"]["deterministic_valuation"] == "pending:deterministic_valuation"


def _seed_facts_and_doc(db: Session, company_id: int):
    from app.models.entities import Document, FinancialFact

    db.add(FinancialFact(
        company_id=company_id, metric="revenue", value=100, period="FY2024",
        fiscal_year=2024, source_type="SEC", confidence=0.95,
    ))
    db.add(FinancialFact(
        company_id=company_id, metric="revenue", value=110, period="FY2025",
        fiscal_year=2025, source_type="SEC", confidence=0.90,
    ))
    db.add(FinancialFact(
        company_id=company_id, metric="eps", value=1.5, period="FY2025",
        fiscal_year=2025, source_type="FMP", confidence=0.40,
    ))
    db.add(Document(company_id=company_id, title="10-K", source_type="SEC"))
    db.commit()


def test_source_audit_probe_reports_observed_distribution(db):
    company = _company(db)
    _seed_facts_and_doc(db, company.id)
    with sqlite_checkpointer() as saver:
        graph = build_thesis_graph(checkpointer=saver, session_factory=_Scope(db))
        graph.invoke({"ticker": "AAPL", "tenant_id": "t1"}, config=_config("t:a1"))
        state = graph.get_state(_config("t:a1")).values
    assert state["artifacts"]["source_audit"] == (
        "audit:facts={FMP:1,SEC:2}|docs={SEC:1}|lowconf=1"
    )
    assert state["meta"]["source_audit"] == {
        "facts_by_source_type": {"SEC": 2, "FMP": 1},
        "documents_by_source_type": {"SEC": 1},
        "low_confidence_facts": 1,
    }


def test_source_audit_probe_honest_empty(db):
    _company(db)
    with sqlite_checkpointer() as saver:
        graph = build_thesis_graph(checkpointer=saver, session_factory=_Scope(db))
        graph.invoke({"ticker": "AAPL", "tenant_id": "t1"}, config=_config("t:a2"))
        state = graph.get_state(_config("t:a2")).values
    assert state["artifacts"]["source_audit"] == "audit:facts={}|docs={}|lowconf=0"


def test_source_audit_skeleton_without_session_factory():
    with sqlite_checkpointer() as saver:
        graph = build_thesis_graph(checkpointer=saver)
        graph.invoke({"ticker": "AAPL", "tenant_id": "t1"}, config=_config("t:a3"))
        state = graph.get_state(_config("t:a3")).values
    assert state["artifacts"]["source_audit"] == "pending:source_audit"


def test_red_team_probe_reads_latest_run(db):
    from app.models.entities import RedTeamRun

    company = _company(db)
    db.add(RedTeamRun(company_id=company.id, status="completed", score=72,
                      prompt_version="red-team-v1"))
    db.commit()
    with sqlite_checkpointer() as saver:
        graph = build_thesis_graph(checkpointer=saver, session_factory=_Scope(db))
        graph.invoke({"ticker": "AAPL", "tenant_id": "t1"}, config=_config("t:rt1"))
        state = graph.get_state(_config("t:rt1")).values
    assert state["artifacts"]["deterministic_red_team"] == "redteam:1:score=72"
    assert state["meta"]["red_team_run"] == {
        "id": 1,
        "status": "completed",
        "score": 72,
        "prompt_version": "red-team-v1",
    }


def test_red_team_probe_honest_none(db):
    _company(db)
    with sqlite_checkpointer() as saver:
        graph = build_thesis_graph(checkpointer=saver, session_factory=_Scope(db))
        graph.invoke({"ticker": "AAPL", "tenant_id": "t1"}, config=_config("t:rt2"))
        state = graph.get_state(_config("t:rt2")).values
    assert state["artifacts"]["deterministic_red_team"] == "redteam:none"
    assert state["meta"]["red_team_run"] is None


def test_red_team_skeleton_without_session_factory():
    with sqlite_checkpointer() as saver:
        graph = build_thesis_graph(checkpointer=saver)
        graph.invoke({"ticker": "AAPL", "tenant_id": "t1"}, config=_config("t:rt3"))
        state = graph.get_state(_config("t:rt3")).values
    assert state["artifacts"]["deterministic_red_team"] == "pending:deterministic_red_team"
