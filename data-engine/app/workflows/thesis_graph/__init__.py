"""LangGraph thesis lifecycle pilot (workflow stage 6).

Shadow pilot ONLY: the classic ThesisService.generate() path remains the
source of truth. This package builds the target graph skeleton with durable
checkpointing; shadow comparison (6b) and the approval interrupt (6c) land
in follow-up PRs. See docs in graph.py for the design rules.
"""

from app.workflows.thesis_graph.checkpointer import thesis_thread_id
from app.workflows.thesis_graph.graph import THESIS_GRAPH_NODES, build_thesis_graph

__all__ = ["THESIS_GRAPH_NODES", "build_thesis_graph", "thesis_thread_id"]
