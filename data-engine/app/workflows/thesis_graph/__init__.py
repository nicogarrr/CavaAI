"""LangGraph thesis lifecycle (workflow stage 6).

The graph is the durable CONTROL PLANE of the thesis lifecycle: crash-safe
resume under a checkpointer, a real approval ``interrupt()``, idempotent
retry and read-side probes of what the classic ``ThesisService.generate()``
path persisted. The classic path remains the sole LLM/write executor.

Every node has a real implementation and commits a real artifact reference;
``build_thesis_graph`` requires a ``session_factory`` and refuses to compile
into placeholders. See ``graph.py`` for the node-by-node contract and for the
nodes retired from the graph (and what replaced them).
"""

from app.workflows.thesis_graph.checkpointer import thesis_thread_id
from app.workflows.thesis_graph.graph import THESIS_GRAPH_NODES, build_thesis_graph

__all__ = ["THESIS_GRAPH_NODES", "build_thesis_graph", "thesis_thread_id"]