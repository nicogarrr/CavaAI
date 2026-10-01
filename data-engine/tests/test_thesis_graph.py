"""Thesis graph: compile, checkpoint, resume, idempotency, approval interrupt.

Every node in the graph commits a real artifact reference. These tests also
pin the honesty boundary: no node may emit a ``pending:<node>`` stand-in, and
the graph refuses to compile without the session its probes need.
"""

import pytest
from langgraph.types import Command
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, Company, ThesisVersion
from app.workflows.thesis_graph import THESIS_GRAPH_NODES, build_thesis_graph, thesis_thread_id
from app.workflows.thesis_graph.checkpointer import sqlite_checkpointer


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def company(db):
    row = Company(
        ticker="AAPL", name="Apple", exchange="NASDAQ", currency="USD",
        sector="Tech", industry="Tech", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(row)
    db.commit()
    return row


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


def _resume_approve(graph, thread_id: str):
    return graph.invoke(
        Command(resume={"decision": "approve", "actor": "test"}),
        config=_config(thread_id),
    )


def _publish(db, version: int = 1) -> None:
    db.add(
        ThesisVersion(
            company_id=1, version=version, status="published",
            thesis_markdown="# t", executive_summary="s",
        )
    )
    db.commit()


def test_thread_id_format():
    tid = thesis_thread_id("t1", "c42", "fp-abc")
    assert tid == "thesis:t1:c42:fp-abc"


def test_graph_refuses_to_compile_without_a_session_factory():
    """Un probe sin sesion solo podria emitir un placeholder: se niega a existir."""
    with pytest.raises(ValueError, match="session_factory is required"):
        build_thesis_graph()


def test_graph_compiles_without_checkpointer(db):
    assert build_thesis_graph(session_factory=_Scope(db)) is not None


def test_no_graph_node_is_a_placeholder():
    retired = {"optional_bull_bear_debate", "publish"}
    assert retired.isdisjoint(THESIS_GRAPH_NODES)
    assert "persisted_thesis" in THESIS_GRAPH_NODES
    assert "assemble_candidate" in THESIS_GRAPH_NODES


def test_full_run_records_all_nodes_in_order_and_no_pending_artifact(db, company):
    _publish(db)
    with sqlite_checkpointer() as saver:
        graph = build_thesis_graph(checkpointer=saver, session_factory=_Scope(db))
        graph.invoke({"ticker": "AAPL", "tenant_id": "t1"}, config=_config("thesis:t1:c1:fp1"))
        result = _resume_approve(graph, "thesis:t1:c1:fp1")
    assert result["completed_nodes"] == list(THESIS_GRAPH_NODES)
    assert result["status"] == "published"
    assert set(result["artifacts"]) == set(THESIS_GRAPH_NODES)
    for name, ref in result["artifacts"].items():
        assert not ref.startswith("pending:"), name
        assert ref.strip(), name
    assert result["artifacts"]["resolve_company"] == f"company:{company.id}"
    assert result["artifacts"]["freeze_input_snapshot"].startswith("sha256:")
    assert result["artifacts"]["persisted_thesis"] == "thesis_published:v1"
    assert result["artifacts"]["assemble_candidate"].startswith("candidate:sha256:")


def test_crash_resume_skips_committed_nodes(db, company):
    """A crash after node N, then re-invoking the same thread, must not
    re-execute committed nodes (checkpoint resume, not a fresh run)."""
    crash_at = "source_audit"
    executed: list[str] = []

    import app.workflows.thesis_graph.graph as graph_mod

    original = graph_mod._NODE_BUILDERS["source_audit"]

    def counting_node(session_factory):
        node = original(session_factory)

        def wrapper(state):
            executed.append(crash_at)
            if executed.count(crash_at) == 1:
                raise RuntimeError("simulated crash")
            return node(state)

        return wrapper

    graph_mod._NODE_BUILDERS["source_audit"] = counting_node
    try:
        with sqlite_checkpointer() as saver:
            graph = build_thesis_graph(checkpointer=saver, session_factory=_Scope(db))
            tid = "thesis:t1:c2:fp2"
            with pytest.raises(RuntimeError):
                graph.invoke({"ticker": "AAPL", "tenant_id": "t1"}, config=_config(tid))
            first_pass = list(executed)
            assert crash_at in first_pass

            # resume: None input continues from the last checkpoint; the run
            # then pauses at the approval interrupt.
            graph.invoke(None, config=_config(tid))
            assert graph.get_state(_config(tid)).next == ("approval_gate",)
            result = _resume_approve(graph, tid)
            assert result["status"] == "approved"
            assert result["completed_nodes"] == list(THESIS_GRAPH_NODES)
    finally:
        graph_mod._NODE_BUILDERS["source_audit"] = original

    committed_before_crash = [n for n in first_pass if n != crash_at]
    resumed_pass = executed[len(first_pass):]
    # the crashed node retries; every node committed before the crash does NOT re-run
    assert not set(committed_before_crash) & set(resumed_pass)
    assert resumed_pass.count(crash_at) == 1


def test_duplicate_delivery_is_idempotent(db, company):
    _publish(db)
    with sqlite_checkpointer() as saver:
        graph = build_thesis_graph(checkpointer=saver, session_factory=_Scope(db))
        tid = "thesis:t1:c3:fp3"
        graph.invoke({"ticker": "AAPL", "tenant_id": "t1"}, config=_config(tid))
        first = _resume_approve(graph, tid)
        second = graph.invoke({"ticker": "AAPL", "tenant_id": "t1"}, config=_config(tid))
    assert second["completed_nodes"] == first["completed_nodes"] == list(THESIS_GRAPH_NODES)
    assert second["artifacts"] == first["artifacts"]


def test_approval_gate_interrupts_before_persisted_thesis(db, company):
    with sqlite_checkpointer() as saver:
        graph = build_thesis_graph(checkpointer=saver, session_factory=_Scope(db))
        tid = "thesis:t1:c4:fp4"
        graph.invoke({"ticker": "AAPL", "tenant_id": "t1"}, config=_config(tid))
        snapshot = graph.get_state(_config(tid))
        assert snapshot.next == ("approval_gate",)
        interrupts = [i for task in snapshot.tasks for i in task.interrupts]
        assert interrupts and interrupts[0].value["type"] == "thesis_approval"
        # the gate pauses before any publication claim is made
        assert "persisted_thesis" not in snapshot.values["completed_nodes"]
        # the payload shows what is being approved, not an empty placeholder
        assert interrupts[0].value["candidate"]["observations"]
        result = _resume_approve(graph, tid)
    nodes = result["completed_nodes"]
    assert nodes.index("approval_gate") < nodes.index("persisted_thesis")
    assert result["artifacts"]["approval_gate"] == "approval:approve"
    assert result["meta"]["approval"]["decision"] == "approve"


def test_request_changes_ends_run_without_publication_node(db, company):
    with sqlite_checkpointer() as saver:
        graph = build_thesis_graph(checkpointer=saver, session_factory=_Scope(db))
        tid = "thesis:t1:c5:fp5"
        graph.invoke({"ticker": "AAPL", "tenant_id": "t1"}, config=_config(tid))
        result = graph.invoke(
            Command(resume={"decision": "request_changes", "notes": "redo valuation"}),
            config=_config(tid),
        )
    assert result["status"] == "changes_requested"
    assert "persisted_thesis" not in result["completed_nodes"]
    assert result["artifacts"]["approval_gate"] == "approval:request_changes"
    assert result["meta"]["approval"] == {
        "decision": "request_changes",
        "notes": "redo valuation",
        "actor": None,
    }


def test_approval_never_claims_a_publication_that_did_not_happen(db, company):
    """Sin ThesisVersion publicada, aprobar termina en 'approved', no 'published'."""
    with sqlite_checkpointer() as saver:
        graph = build_thesis_graph(checkpointer=saver, session_factory=_Scope(db))
        tid = "thesis:t1:c6:fp6"
        graph.invoke({"ticker": "AAPL", "tenant_id": "t1"}, config=_config(tid))
        result = _resume_approve(graph, tid)
    assert result["status"] == "approved"
    assert result["artifacts"]["persisted_thesis"] == "thesis:none"
    assert result["meta"]["published_thesis"] is None


def test_draft_version_that_is_not_published_stays_approved(db, company):
    db.add(
        ThesisVersion(
            company_id=1, version=1, status="draft",
            thesis_markdown="# t", executive_summary="s",
        )
    )
    db.commit()
    with sqlite_checkpointer() as saver:
        graph = build_thesis_graph(checkpointer=saver, session_factory=_Scope(db))
        tid = "thesis:t1:c7:fp7"
        graph.invoke({"ticker": "AAPL", "tenant_id": "t1"}, config=_config(tid))
        result = _resume_approve(graph, tid)
    assert result["status"] == "approved"
    assert result["artifacts"]["persisted_thesis"] == "thesis_unpublished:v1:draft"
    assert result["artifacts"]["draft_synthesis"].startswith("thesis:v1:draft:sections=0:sha=")


def test_invalid_decision_is_rejected_loudly(db, company):
    with sqlite_checkpointer() as saver:
        graph = build_thesis_graph(checkpointer=saver, session_factory=_Scope(db))
        tid = "thesis:t1:c8:fp8"
        graph.invoke({"ticker": "AAPL", "tenant_id": "t1"}, config=_config(tid))
        with pytest.raises(Exception):
            graph.invoke(
                Command(resume={"decision": "maybe"}),
                config=_config(tid),
            )