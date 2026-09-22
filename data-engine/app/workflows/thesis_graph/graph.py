"""Target thesis lifecycle graph (stage 6a: skeleton + checkpointing).

Target flow (assessment §2):
    resolve_company -> freeze_input_snapshot -> ensure_ingestion_complete
    -> build_fundamental_model -> deterministic_valuation -> draft_synthesis
    -> source_audit -> deterministic_red_team -> optional_bull_bear_debate
    -> assemble_candidate -> approval_gate -> publish

Design rules carried from the assessment:
- Nodes are short and idempotent; each commits a durable domain artifact and
  writes only its ID/hash into state. Skeleton nodes record the node name in
  ``completed_nodes`` and a placeholder artifact reference; real logic lands
  in 6b (shadow comparison) and 6c (approval interrupt).
- Financial calculations, source hierarchy, publishability gates and score
  math stay deterministic Python nodes. LLM nodes are limited to synthesis,
  debate and qualitative challenge; a model never writes published state.
- The approval gate becomes a real ``interrupt()`` in 6c, in its own node
  with no side effects before the interrupt (a node restarts from the
  beginning on resume). Publishing happens in the following idempotent node.
- thread_id = thesis:{tenant_id}:{company_id}:{input_fingerprint}, so a
  Dramatiq retry resumes the same thread instead of starting a second thesis.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

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
        if name == "approval_gate":
            update["status"] = "awaiting_approval"
        elif name == "publish":
            update["status"] = "published"
        else:
            update["status"] = "running"
        return update

    node.__name__ = name
    return node


def build_thesis_graph(checkpointer=None):
    """Compile the thesis lifecycle graph with an optional checkpointer.

    Pass a LangGraph checkpointer (PostgresSaver in prod, SqliteSaver in
    tests). Without one the graph still compiles for shape/structure tests,
    but crash recovery and resume require a durable checkpointer.
    """
    graph = StateGraph(ThesisGraphState)
    for name in THESIS_GRAPH_NODES:
        graph.add_node(name, _make_skeleton_node(name))
    graph.add_edge(START, THESIS_GRAPH_NODES[0])
    for previous, following in zip(THESIS_GRAPH_NODES, THESIS_GRAPH_NODES[1:]):
        graph.add_edge(previous, following)
    graph.add_edge(THESIS_GRAPH_NODES[-1], END)
    return graph.compile(checkpointer=checkpointer)
