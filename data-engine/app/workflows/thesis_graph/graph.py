"""Target thesis lifecycle graph (stage 6a skeleton + 6c approval interrupt).

Target flow (assessment §2):
    resolve_company -> freeze_input_snapshot -> ensure_ingestion_complete
    -> build_fundamental_model -> deterministic_valuation -> draft_synthesis
    -> source_audit -> deterministic_red_team -> optional_bull_bear_debate
    -> assemble_candidate -> approval_gate -> publish

Design rules carried from the assessment:
- Nodes are short and idempotent; each commits a durable domain artifact and
  writes only its ID/hash into state. Skeleton nodes record the node name in
  ``completed_nodes`` and a placeholder artifact reference; real logic lands
  progressively (6b shadow comparison, 6c approval interrupt).
- Financial calculations, source hierarchy, publishability gates and score
  math stay deterministic Python nodes. LLM nodes are limited to synthesis,
  debate and qualitative challenge; a model never writes published state.
- The approval gate is a real ``interrupt()`` (6c) in its own node with no
  side effects before the interrupt (a node restarts from the beginning on
  resume). Publishing happens in the following idempotent node, and only
  after an explicit ``approve`` decision; ``request_changes`` ends the run
  with status ``changes_requested`` and the decision recorded in metadata.
- thread_id = thesis:{tenant_id}:{company_id}:{input_fingerprint}, so a
  Dramatiq retry resumes the same thread instead of starting a second thesis.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.workflows.thesis_graph.state import ThesisGraphState

THESIS_GRAPH_NODES: tuple[str, ...] = (
    "resolve_company",
    "freeze_input_snapshot",
    "ensure_ingestion_complete",
    "build_fundamental_model",
    "deterministic_valuation",
    "draft_synthesis",
    "source_audit",
    "deterministic_red_team",
    "optional_bull_bear_debate",
    "assemble_candidate",
    "approval_gate",
    "publish",
)

APPROVAL_DECISIONS: tuple[str, ...] = ("approve", "request_changes")


def _make_skeleton_node(name: str):
    """Idempotent skeleton node: records its artifact reference once.

    If the node already committed (present in state['artifacts']), it is a
    no-op, which makes duplicate Dramatiq delivery safe at the skeleton
    level. Real nodes keep this contract via idempotency keys.
    """

    def node(state: ThesisGraphState) -> dict:
        artifacts = dict(state.get("artifacts") or {})
        if name in artifacts:
            return {}
        artifacts[name] = f"pending:{name}"
        update: dict = {"artifacts": artifacts, "completed_nodes": [name]}
        if name == "publish":
            update["status"] = "published"
        else:
            update["status"] = "running"
        return update

    node.__name__ = name
    return node


def _approval_gate_node(state: ThesisGraphState) -> dict:
    """Stage 6c: real approval interrupt with an idempotent resume contract.

    Nothing mutates before ``interrupt()``: the payload only reads control
    state (a node restarts from the beginning on resume). The resume value
    must be ``{"decision": "approve"}`` or
    ``{"decision": "request_changes", "notes": <str>}``; the decision is
    recorded in ``meta.approval`` and the conditional edge after this node
    routes approved runs to ``publish`` and everything else to ``END``.
    """
    artifacts = dict(state.get("artifacts") or {})
    if "approval_gate" in artifacts:
        # Idempotent re-delivery on an already-decided thread.
        return {}
    decision: dict[str, Any] = interrupt(
        {
            "type": "thesis_approval",
            "ticker": state.get("ticker"),
            "candidate_artifact": artifacts.get("assemble_candidate"),
            "completed_nodes": list(state.get("completed_nodes") or []),
            "expected_decisions": list(APPROVAL_DECISIONS),
        }
    ) or {}
    choice = decision.get("decision")
    if choice not in APPROVAL_DECISIONS:
        raise ValueError(f"approval decision must be one of {APPROVAL_DECISIONS}")
    artifacts["approval_gate"] = "pending:approval_gate"
    meta = dict(state.get("meta") or {})
    meta["approval"] = {
        "decision": choice,
        "notes": decision.get("notes"),
        "actor": decision.get("actor"),
    }
    return {
        "artifacts": artifacts,
        "completed_nodes": ["approval_gate"],
        "status": "running" if choice == "approve" else "changes_requested",
        "meta": meta,
    }


def _route_after_approval(state: ThesisGraphState) -> str:
    approval = (state.get("meta") or {}).get("approval") or {}
    return "publish" if approval.get("decision") == "approve" else END


def build_thesis_graph(checkpointer=None):
    """Compile the thesis lifecycle graph with an optional checkpointer.

    Pass a LangGraph checkpointer (PostgresSaver in prod, SqliteSaver in
    tests). Without one the graph still compiles for shape/structure tests,
    but crash recovery, the approval interrupt and resume require a durable
    checkpointer.
    """
    graph = StateGraph(ThesisGraphState)
    for name in THESIS_GRAPH_NODES:
        node = _approval_gate_node if name == "approval_gate" else _make_skeleton_node(name)
        graph.add_node(name, node)
    graph.add_edge(START, THESIS_GRAPH_NODES[0])
    for previous, following in zip(THESIS_GRAPH_NODES[:-1], THESIS_GRAPH_NODES[1:-1]):
        graph.add_edge(previous, following)
    graph.add_conditional_edges(
        "approval_gate",
        _route_after_approval,
        {"publish": "publish", END: END},
    )
    graph.add_edge("publish", END)
    return graph.compile(checkpointer=checkpointer)
