"""Stage 6d: real deterministic nodes (resolve_company, freeze_input_snapshot)."""

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
