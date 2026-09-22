"""Thesis lifecycle graph (stage 6 complete: control plane + read probes).

Flow:
    resolve_company -> freeze_input_snapshot -> ensure_ingestion_complete
    -> build_fundamental_model -> deterministic_valuation -> draft_synthesis
    -> source_audit -> deterministic_red_team -> optional_bull_bear_debate
    -> assemble_candidate -> approval_gate -> publish

Stage-6 boundary (final):
- The graph is the durable control plane for the thesis lifecycle:
  crash-safe resume under a checkpointer, a real approval ``interrupt()``,
  idempotent retry, and read-side probes that record the classic path's
  persisted state (resolve_company, ensure_ingestion_complete,
  build_fundamental_model, deterministic_valuation, source_audit,
  deterministic_red_team) plus the freeze_input_snapshot fingerprint.
- The classic ThesisService path remains the SOLE LLM/write executor.
  draft_synthesis, optional_bull_bear_debate, assemble_candidate and
  publish are deliberate control-state placeholders (``pending:<node>``):
  they keep the control flow complete and resumable without duplicating
  LLM cost or risking double writes, and they never execute business work
  inside the graph.
- The approval gate is a real ``interrupt()`` in its own node with no side
  effects before the interrupt (a node restarts from the beginning on
  resume); ``request_changes`` ends the run as ``changes_requested`` with
  the decision recorded in metadata.
- thread_id = thesis:{tenant_id}:{company_id}:{input_fingerprint}, so a
  Dramatiq retry resumes the same thread instead of starting a second thesis.
- The shadow comparison (ThesisShadowService) validates node order,
  idempotent retry and every probe observation against the classic
  persisted state on each run; divergences are recorded explicitly.
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


def _build_fundamental_model_node(session_factory):
    """Read-side deterministic node (stage 6d): latest fundamental model.

    Records the latest persisted FundamentalModelVersion as the artifact
    (version + input fingerprint prefix), or an honest ``model:none``.
    The graph never writes model artifacts at this stage: the classic
    ThesisService path builds and persists models.
    """

    def node(state: ThesisGraphState) -> dict:
        artifacts = dict(state.get("artifacts") or {})
        if "build_fundamental_model" in artifacts:
            return {}
        if session_factory is None:
            artifacts["build_fundamental_model"] = "pending:build_fundamental_model"
            return {
                "artifacts": artifacts,
                "completed_nodes": ["build_fundamental_model"],
                "status": "running",
            }
        company_id = state.get("company_id")
        if not company_id:
            raise ValueError("build_fundamental_model requires company_id")
        from sqlalchemy import desc, select

        from app.models.entities import FundamentalModelVersion

        with session_factory() as db:
            model = db.scalar(
                select(FundamentalModelVersion)
                .where(FundamentalModelVersion.company_id == int(company_id))
                .order_by(desc(FundamentalModelVersion.version))
                .limit(1)
            )
        meta = dict(state.get("meta") or {})
        if model is None:
            artifacts["build_fundamental_model"] = "model:none"
            meta["fundamental_model"] = None
        else:
            artifacts["build_fundamental_model"] = (
                f"model:v{model.version}:{model.input_fingerprint[:12]}"
            )
            meta["fundamental_model"] = {
                "version": model.version,
                "status": model.status,
                "publishable": model.publishable,
                "framework_key": model.framework_key,
            }
        return {
            "artifacts": artifacts,
            "completed_nodes": ["build_fundamental_model"],
            "status": "running",
            "meta": meta,
        }

    node.__name__ = "build_fundamental_model"
    return node


def _deterministic_valuation_node(session_factory):
    """Read-side deterministic node (stage 6d): latest valuation snapshot.

    Records the latest persisted FundamentalValuationSnapshot id and
    fingerprint, or an honest ``valuation:none``. The graph never computes
    or writes valuations at this stage.
    """

    def node(state: ThesisGraphState) -> dict:
        artifacts = dict(state.get("artifacts") or {})
        if "deterministic_valuation" in artifacts:
            return {}
        if session_factory is None:
            artifacts["deterministic_valuation"] = "pending:deterministic_valuation"
            return {
                "artifacts": artifacts,
                "completed_nodes": ["deterministic_valuation"],
                "status": "running",
            }
        company_id = state.get("company_id")
        if not company_id:
            raise ValueError("deterministic_valuation requires company_id")
        from sqlalchemy import desc, select

        from app.models.entities import FundamentalValuationSnapshot

        with session_factory() as db:
            snapshot = db.scalar(
                select(FundamentalValuationSnapshot)
                .where(FundamentalValuationSnapshot.company_id == int(company_id))
                .order_by(
                    desc(FundamentalValuationSnapshot.created_at),
                    desc(FundamentalValuationSnapshot.id),
                )
                .limit(1)
            )
        meta = dict(state.get("meta") or {})
        if snapshot is None:
            artifacts["deterministic_valuation"] = "valuation:none"
            meta["valuation_snapshot"] = None
        else:
            artifacts["deterministic_valuation"] = f"valuation:{snapshot.id}"
            meta["valuation_snapshot"] = {
                "id": snapshot.id,
                "fingerprint": snapshot.valuation_snapshot_fingerprint[:12],
                "current_price": (
                    float(snapshot.current_price)
                    if snapshot.current_price is not None
                    else None
                ),
            }
        return {
            "artifacts": artifacts,
            "completed_nodes": ["deterministic_valuation"],
            "status": "running",
            "meta": meta,
        }

    node.__name__ = "deterministic_valuation"
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


def _source_audit_node(session_factory):
    """Read-side deterministic node (stage 6e): evidence provenance audit.

    Records the observed distribution of persisted FinancialFact and
    Document rows by ``source_type`` (sorted, deterministic) plus the
    count of low-confidence facts (< 0.5). source_type is a free-form
    vocabulary (SEC, FMP, FRED, IR, seed, ...); the probe reports the
    observed distribution verbatim and never invents a classification.
    Read-only: the classic path owns audit interpretation; the graph
    never writes audit artifacts.
    """

    def node(state: ThesisGraphState) -> dict:
        artifacts = dict(state.get("artifacts") or {})
        if "source_audit" in artifacts:
            return {}
        if session_factory is None:
            artifacts["source_audit"] = "pending:source_audit"
            return {
                "artifacts": artifacts,
                "completed_nodes": ["source_audit"],
                "status": "running",
            }
        company_id = state.get("company_id")
        if not company_id:
            raise ValueError("source_audit requires company_id")
        from sqlalchemy import func, select

        from app.models import Document, FinancialFact

        with session_factory() as db:
            cid = int(company_id)
            fact_rows = db.execute(
                select(FinancialFact.source_type, func.count())
                .where(FinancialFact.company_id == cid)
                .group_by(FinancialFact.source_type)
            ).all()
            doc_rows = db.execute(
                select(Document.source_type, func.count())
                .where(Document.company_id == cid)
                .group_by(Document.source_type)
            ).all()
            low_confidence = db.scalar(
                select(func.count())
                .select_from(FinancialFact)
                .where(FinancialFact.company_id == cid, FinancialFact.confidence < 0.5)
            ) or 0
        facts_by_source = {str(src): count for src, count in fact_rows}
        docs_by_source = {str(src): count for src, count in doc_rows}
        facts_part = ",".join(f"{k}:{facts_by_source[k]}" for k in sorted(facts_by_source))
        docs_part = ",".join(f"{k}:{docs_by_source[k]}" for k in sorted(docs_by_source))
        artifacts["source_audit"] = (
            f"audit:facts={{{facts_part}}}|docs={{{docs_part}}}|lowconf={low_confidence}"
        )
        meta = dict(state.get("meta") or {})
        meta["source_audit"] = {
            "facts_by_source_type": facts_by_source,
            "documents_by_source_type": docs_by_source,
            "low_confidence_facts": low_confidence,
        }
        return {
            "artifacts": artifacts,
            "completed_nodes": ["source_audit"],
            "status": "running",
            "meta": meta,
        }

    node.__name__ = "source_audit"
    return node


def _deterministic_red_team_node(session_factory):
    """Read-side deterministic node (stage 6e): latest red-team run.

    Records the latest persisted RedTeamRun (id, status, score,
    prompt_version) as the node artifact + state metadata, or an honest
    ``redteam:none``. The graph never runs or writes red-team artifacts
    at this stage: the classic RedTeamService path owns them.
    """

    def node(state: ThesisGraphState) -> dict:
        artifacts = dict(state.get("artifacts") or {})
        if "deterministic_red_team" in artifacts:
            return {}
        if session_factory is None:
            artifacts["deterministic_red_team"] = "pending:deterministic_red_team"
            return {
                "artifacts": artifacts,
                "completed_nodes": ["deterministic_red_team"],
                "status": "running",
            }
        company_id = state.get("company_id")
        if not company_id:
            raise ValueError("deterministic_red_team requires company_id")
        from sqlalchemy import desc, select

        from app.models.entities import RedTeamRun

        with session_factory() as db:
            run = db.scalar(
                select(RedTeamRun)
                .where(RedTeamRun.company_id == int(company_id))
                .order_by(desc(RedTeamRun.created_at), desc(RedTeamRun.id))
                .limit(1)
            )
        meta = dict(state.get("meta") or {})
        if run is None:
            artifacts["deterministic_red_team"] = "redteam:none"
            meta["red_team_run"] = None
        else:
            artifacts["deterministic_red_team"] = f"redteam:{run.id}:score={run.score}"
            meta["red_team_run"] = {
                "id": run.id,
                "status": run.status,
                "score": run.score,
                "prompt_version": run.prompt_version,
            }
        return {
            "artifacts": artifacts,
            "completed_nodes": ["deterministic_red_team"],
            "status": "running",
            "meta": meta,
        }

    node.__name__ = "deterministic_red_team"
    return node


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
        elif name == "build_fundamental_model":
            node = _build_fundamental_model_node(session_factory)
        elif name == "deterministic_valuation":
            node = _deterministic_valuation_node(session_factory)
        elif name == "source_audit":
            node = _source_audit_node(session_factory)
        elif name == "deterministic_red_team":
            node = _deterministic_red_team_node(session_factory)
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
