"""Stage 6a+6c: thesis graph - compile, checkpoint, resume, idempotency, approval interrupt."""

import pytest
from langgraph.types import Command

from app.workflows.thesis_graph import THESIS_GRAPH_NODES, build_thesis_graph, thesis_thread_id
from app.workflows.thesis_graph.checkpointer import sqlite_checkpointer


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _resume_approve(graph, thread_id: str):
    return graph.invoke(
        Command(resume={"decision": "approve", "actor": "test"}),
        config=_config(thread_id),
    )


def test_thread_id_format():
    tid = thesis_thread_id("t1", "c42", "fp-abc")
    assert tid == "thesis:t1:c42:fp-abc"


def test_graph_compiles_without_checkpointer():
    graph = build_thesis_graph()
    assert graph is not None


def test_full_run_records_all_nodes_in_order():
    with sqlite_checkpointer() as saver:
        graph = build_thesis_graph(checkpointer=saver)
        graph.invoke({"ticker": "AAPL", "tenant_id": "t1"}, config=_config("thesis:t1:c1:fp1"))
        result = _resume_approve(graph, "thesis:t1:c1:fp1")
    assert result["completed_nodes"] == list(THESIS_GRAPH_NODES)
    assert result["status"] == "published"
    # freeze_input_snapshot is a real deterministic node (6d) and writes a
    # sha256 ref; the rest stay skeleton references at this stage.
    for name, ref in result["artifacts"].items():
        if name == "freeze_input_snapshot":
            assert ref.startswith("sha256:")
        else:
            assert ref == f"pending:{name}"


def test_crash_resume_skips_committed_nodes():
    """A crash after node N, then re-invoking the same thread, must not
    re-execute committed nodes (checkpoint resume, not a fresh run)."""
    crash_at = "draft_synthesis"  # still a skeleton node; deterministic_valuation is real (6d)
    executed: list[str] = []

    import app.workflows.thesis_graph.graph as graph_mod

    original = graph_mod._make_skeleton_node

    def counting_node(name):
        node = original(name)

        def wrapper(state):
            executed.append(name)
            if name == crash_at and executed.count(name) == 1:
                raise RuntimeError("simulated crash")
            return node(state)

        return wrapper

    graph_mod._make_skeleton_node = counting_node
    try:
        with sqlite_checkpointer() as saver:
            graph = build_thesis_graph(checkpointer=saver)
            tid = "thesis:t1:c2:fp2"
            with pytest.raises(RuntimeError):
                graph.invoke({"ticker": "MSFT", "tenant_id": "t1"}, config=_config(tid))
            first_pass = list(executed)
            assert crash_at in first_pass  # crashed at the intended node

            # resume: None input continues from the last checkpoint; the run
            # then pauses at the 6c approval interrupt before publish.
            graph.invoke(None, config=_config(tid))
            assert graph.get_state(_config(tid)).next == ("approval_gate",)
            result = _resume_approve(graph, tid)
            assert result["status"] == "published"
            assert result["completed_nodes"] == list(THESIS_GRAPH_NODES)
    finally:
        graph_mod._make_skeleton_node = original

    committed_before_crash = [n for n in first_pass if n != crash_at]
    resumed_pass = executed[len(first_pass):]
    # the crashed node retries; every node committed before the crash does NOT re-run
    assert not set(committed_before_crash) & set(resumed_pass), (
        f"re-executed after resume: {set(committed_before_crash) & set(resumed_pass)}"
    )
    assert resumed_pass.count(crash_at) == 1  # retried exactly once


def test_duplicate_delivery_is_idempotent():
    """Re-invoking a completed thread (at-least-once delivery) changes nothing."""
    with sqlite_checkpointer() as saver:
        graph = build_thesis_graph(checkpointer=saver)
        tid = "thesis:t1:c3:fp3"
        graph.invoke({"ticker": "NVDA", "tenant_id": "t1"}, config=_config(tid))
        first = _resume_approve(graph, tid)
        second = graph.invoke({"ticker": "NVDA", "tenant_id": "t1"}, config=_config(tid))
    assert second["completed_nodes"] == first["completed_nodes"] == list(THESIS_GRAPH_NODES)
    assert second["artifacts"] == first["artifacts"]


def test_approval_gate_interrupts_before_publish():
    with sqlite_checkpointer() as saver:
        graph = build_thesis_graph(checkpointer=saver)
        tid = "thesis:t1:c4:fp4"
        graph.invoke({"ticker": "GOOG", "tenant_id": "t1"}, config=_config(tid))
        snapshot = graph.get_state(_config(tid))
        assert snapshot.next == ("approval_gate",)
        interrupts = [i for task in snapshot.tasks for i in task.interrupts]
        assert interrupts and interrupts[0].value["type"] == "thesis_approval"
        # the gate pauses before anything is published
        assert "publish" not in snapshot.values["completed_nodes"]
        result = _resume_approve(graph, tid)
        nodes = result["completed_nodes"]
        assert nodes.index("approval_gate") < nodes.index("publish")
        assert result["artifacts"]["approval_gate"] == "pending:approval_gate"
        assert result["meta"]["approval"]["decision"] == "approve"


def test_request_changes_ends_run_without_publish():
    with sqlite_checkpointer() as saver:
        graph = build_thesis_graph(checkpointer=saver)
        tid = "thesis:t1:c5:fp5"
        graph.invoke({"ticker": "MSFT", "tenant_id": "t1"}, config=_config(tid))
        result = graph.invoke(
            Command(resume={"decision": "request_changes", "notes": "redo valuation"}),
            config=_config(tid),
        )
    assert result["status"] == "changes_requested"
    assert "publish" not in result["completed_nodes"]
    assert result["meta"]["approval"] == {
        "decision": "request_changes",
        "notes": "redo valuation",
        "actor": None,
    }
