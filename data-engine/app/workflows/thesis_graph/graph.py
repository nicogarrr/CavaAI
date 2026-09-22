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

import hashlib
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


def _resolve_company_node(session_factory):
    """Real deterministic node (stage 6d): resolve the ticker to a Company.

    With no session factory (shape/structure runs) it keeps the skeleton
    reference. With one, an unknown ticker raises - the run fails loudly and
    the checkpoint preserves progress; a company is never invented.
    """

    def node(state: ThesisGraphState) -> dict:
        artifacts = dict(state.get("artifacts") or {})
        if "resolve_company" in artifacts:
            return {}
        if session_factory is None:
            artifacts["resolve_company"] = "pending:resolve_company"
            return {
                "artifacts": artifacts,
                "completed_nodes": ["resolve_company"],
                "status": "running",
            }
        from sqlalchemy import select

        from app.models import Company

        with session_factory() as db:
            company = db.scalar(
                select(Company).where(Company.ticker == (state.get("ticker") or "").upper())
            )
        if company is None:
            raise ValueError(f"unknown_company:{state.get('ticker')}")
        artifacts["resolve_company"] = f"company:{company.id}"
        return {
            "artifacts": artifacts,
            "completed_nodes": ["resolve_company"],
            "status": "running",
            "company_id": str(company.id),
        }

    node.__name__ = "resolve_company"
    return node


def _freeze_input_snapshot_node():
    """Real deterministic node (stage 6d): freeze a stable input fingerprint.

    Records a sha256 over (ticker, company_id, tenant_id) as the node
    artifact. A caller-provided input_fingerprint (e.g. the thread id seed)
    always wins; the node only fills it when absent.
    """

    def node(state: ThesisGraphState) -> dict:
        artifacts = dict(state.get("artifacts") or {})
        if "freeze_input_snapshot" in artifacts:
            return {}
        payload = "|".join(
            [
                (state.get("ticker") or "").upper(),
                str(state.get("company_id") or ""),
                str(state.get("tenant_id") or ""),
            ]
        )
        fingerprint = hashlib.sha256(payload.encode()).hexdigest()[:16]
        artifacts["freeze_input_snapshot"] = f"sha256:{fingerprint}"
        update: dict = {
            "artifacts": artifacts,
            "completed_nodes": ["freeze_input_snapshot"],
            "status": "running",
        }
        if not state.get("input_fingerprint"):
            update["input_fingerprint"] = fingerprint
        return update

    node.__name__ = "freeze_input_snapshot"
    return node


def _ensure_ingestion_complete_node(session_factory):
    """Real deterministic node (stage 6d): evidence coverage probe.

    Read-only: counts the persisted evidence the classic pipeline models
    from (financial facts, market prices, documents) and records the counts
    as the node artifact + state metadata. Zero coverage is an honest
    state, never an error; the node never triggers network ingestion (the
    classic ThesisService path owns that) and never claims completeness it
    cannot verify.
    """

    def node(state: ThesisGraphState) -> dict:
        artifacts = dict(state.get("artifacts") or {})
        if "ensure_ingestion_complete" in artifacts:
            return {}
        if session_factory is None:
            artifacts["ensure_ingestion_complete"] = "pending:ensure_ingestion_complete"
            return {
                "artifacts": artifacts,
                "completed_nodes": ["ensure_ingestion_complete"],
                "status": "running",
            }
        company_id = state.get("company_id")
        if not company_id:
            raise ValueError("ensure_ingestion_complete requires company_id")
        from sqlalchemy import func, select

        from app.models import Document, FinancialFact, MarketPrice

        with session_factory() as db:
            cid = int(company_id)
            facts = db.scalar(
                select(func.count()).select_from(FinancialFact).where(
                    FinancialFact.company_id == cid
                )
            ) or 0
            prices = db.scalar(
                select(func.count()).select_from(MarketPrice).where(
                    MarketPrice.company_id == cid
                )
            ) or 0
            documents = db.scalar(
                select(func.count()).select_from(Document).where(
                    Document.company_id == cid
                )
            ) or 0
        coverage = {"financial_facts": facts, "market_prices": prices, "documents": documents}
        artifacts["ensure_ingestion_complete"] = (
            f"evidence:facts={facts},prices={prices},docs={documents}"
        )
        meta = dict(state.get("meta") or {})
        meta["evidence_coverage"] = coverage
        return {
            "artifacts": artifacts,
            "completed_nodes": ["ensure_ingestion_complete"],
            "status": "running",
            "meta": meta,
        }

    node.__name__ = "ensure_ingestion_complete"
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


def build_thesis_graph(checkpointer=None, session_factory=None):
    """Compile the thesis lifecycle graph with an optional checkpointer.

    Pass a LangGraph checkpointer (PostgresSaver in prod, SqliteSaver in
    tests). Without one the graph still compiles for shape/structure tests,
    but crash recovery, the approval interrupt and resume require a durable
    checkpointer. ``session_factory`` (a contextmanager factory yielding a
    SQLAlchemy Session) turns resolve_company into its real deterministic
    form; without it the node keeps its skeleton reference.
    """
    graph = StateGraph(ThesisGraphState)
    for name in THESIS_GRAPH_NODES:
        if name == "approval_gate":
            node = _approval_gate_node
        elif name == "resolve_company":
            node = _resolve_company_node(session_factory)
        elif name == "freeze_input_snapshot":
            node = _freeze_input_snapshot_node()
        elif name == "ensure_ingestion_complete":
            node = _ensure_ingestion_complete_node(session_factory)
        else:
            node = _make_skeleton_node(name)
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
