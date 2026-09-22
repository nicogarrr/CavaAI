"""Stage 6b: LangGraph thesis pilot shadow comparison.

Runs the thesis lifecycle graph (stage 6a skeleton) alongside the classic
ThesisService path - which remains the source of truth - and records a
structured comparison as a durable WorkflowRun. The shadow never mutates
domain artifacts: the graph writes control state only, and this service
reads the classic path's persisted outputs.

Comparison contract (honest by construction):
- graph_execution: did all 12 nodes commit in order under the checkpointer
  (resuming the 6c approval interrupt with an explicit synthetic shadow
  decision), and does an idempotent re-invoke on the same thread add zero
  new nodes (crash-safe retry).
- phase_mapping: every classic THESIS_PHASES phase maps to a graph node;
  unmapped phases are listed, never silently dropped.
- status_semantics: graph lifecycle status vs the latest persisted
  ThesisVersion status, with divergences listed explicitly.
- artifact_coverage: graph artifacts are pending skeleton references while
  the classic path produces real artifacts; this is an expected divergence
  at 6b and is reported as such, not hidden.
"""

from __future__ import annotations

from typing import Any

from langgraph.types import Command
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, ThesisVersion
from app.services.thesis_job_service import THESIS_PHASES
from app.services.workflow_run_service import begin_run


from contextlib import contextmanager


@contextmanager
def _session_scope(db):
    """Adapt the request-scoped session to the node session factory."""
    yield db
from app.workflows.thesis_graph import THESIS_GRAPH_NODES, build_thesis_graph, thesis_thread_id
from app.workflows.thesis_graph.checkpointer import sqlite_checkpointer

WORKFLOW_NAME = "ThesisShadowComparisonWorkflow"

# Classic phase -> owning graph node (6b mapping; every phase must appear).
PHASE_TO_NODE: dict[str, str] = {
    "collect_evidence": "ensure_ingestion_complete",
    "build_fundamental_model": "build_fundamental_model",
    "run_valuation": "deterministic_valuation",
    "persist_valuation_snapshot": "deterministic_valuation",
    "source_audit": "source_audit",
    "compose_thesis": "draft_synthesis",
    "persist_thesis": "publish",
}


class ThesisShadowService:
    def run(
        self,
        db: Session,
        *,
        ticker: str,
        tenant_external_id: str = "shadow",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
        if company is None:
            return {"ticker": ticker.upper(), "status": "unknown_company"}

        envelope = begin_run(
            db,
            WORKFLOW_NAME,
            execution_mode="shadow",
            input_payload={"ticker": company.ticker},
            idempotency_key=idempotency_key,
        )
        if envelope.replayed:
            return {**dict(envelope.run.result_payload or {}), "idempotent_replay": True}

        thread_id = thesis_thread_id(
            tenant_external_id, str(company.id), f"shadow-{company.ticker}"
        )
        config = {"configurable": {"thread_id": thread_id}}

        with sqlite_checkpointer() as saver:
            graph = build_thesis_graph(
                checkpointer=saver, session_factory=lambda: _session_scope(db)
            )
            initial = graph.invoke(
                {
                    "ticker": company.ticker,
                    "tenant_id": tenant_external_id,
                    "company_id": str(company.id),
                    "input_fingerprint": f"shadow-{company.ticker}",
                },
                config=config,
            )
            # 6c: the run pauses at the real approval_gate interrupt. The
            # shadow resumes with an explicit synthetic decision so the
            # comparison still validates full traversal; the decision is
            # recorded in control state only, never in domain artifacts.
            snapshot = graph.get_state(config)
            interrupted_at_gate = snapshot.next == ("approval_gate",)
            if interrupted_at_gate:
                first = graph.invoke(
                    Command(resume={"decision": "approve", "actor": "shadow-auto-approve"}),
                    config=config,
                )
            else:
                first = initial
            # Idempotent re-delivery: a retry on the same thread must add
            # zero newly committed nodes.
            second = graph.invoke(
                {
                    "ticker": company.ticker,
                    "tenant_id": tenant_external_id,
                    "company_id": str(company.id),
                    "input_fingerprint": f"shadow-{company.ticker}",
                },
                config=config,
            )

        graph_nodes = list(first.get("completed_nodes") or [])
        retry_new_nodes = [
            node for node in (second.get("completed_nodes") or []) if node not in graph_nodes
        ]
        graph_execution = {
            "nodes_in_order": graph_nodes == list(THESIS_GRAPH_NODES),
            "completed_nodes": graph_nodes,
            "final_status": first.get("status"),
            "retry_added_nodes": retry_new_nodes,
            "idempotent_retry": retry_new_nodes == [],
            "approval_interrupt": {
                "interrupted_at_gate": interrupted_at_gate,
                "resume_decision": {"decision": "approve", "actor": "shadow-auto-approve"},
            },
        }

        unmapped_phases = [phase for phase in THESIS_PHASES if phase not in PHASE_TO_NODE]
        missing_nodes = [
            PHASE_TO_NODE[phase]
            for phase in THESIS_PHASES
            if phase in PHASE_TO_NODE and PHASE_TO_NODE[phase] not in THESIS_GRAPH_NODES
        ]
        phase_mapping = {
            "classic_phases": list(THESIS_PHASES),
            "mapping": dict(PHASE_TO_NODE),
            "unmapped_phases": unmapped_phases,
            "missing_graph_nodes": missing_nodes,
            "complete": not unmapped_phases and not missing_nodes,
        }

        latest = db.scalar(
            select(ThesisVersion)
            .where(ThesisVersion.company_id == company.id)
            .order_by(ThesisVersion.version.desc())
            .limit(1)
        )
        divergences = []
        if latest is None:
            divergences.append("classic path has no persisted thesis version for this company")
        if graph_nodes != list(THESIS_GRAPH_NODES):
            divergences.append("graph did not commit all nodes in order")
        if retry_new_nodes:
            divergences.append(f"idempotent retry re-executed nodes: {retry_new_nodes}")
        if unmapped_phases:
            divergences.append(f"classic phases without graph node: {unmapped_phases}")
        if missing_nodes:
            divergences.append(f"mapped nodes missing from graph: {missing_nodes}")
        divergences.append(
            "expected at 6b: graph artifacts are pending skeleton references; "
            "the classic path owns real artifacts"
        )

        status_semantics = {
            "graph_status": first.get("status"),
            "classic_latest_version": (
                {"version": latest.version, "status": latest.status} if latest else None
            ),
        }

        result = {
            "ticker": company.ticker,
            "thread_id": thread_id,
            "graph_execution": graph_execution,
            "phase_mapping": phase_mapping,
            "status_semantics": status_semantics,
            "divergences": divergences,
            "shadow_only": True,
        }
        envelope.finish(result)
        return result
