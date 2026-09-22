"""State schema for the thesis lifecycle graph.

Design rule (assessment §2): nodes write only IDs/hashes into graph state,
never full documents. Durable domain artifacts live in Postgres; this state
is control state only (current node, artifact references, status, error).
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class ThesisGraphState(TypedDict, total=False):
    ticker: str
    tenant_id: str
    company_id: str | None
    input_fingerprint: str | None
    # node name -> durable artifact id/hash (never document contents)
    artifacts: dict[str, str]
    # append-only log of nodes that committed their artifact (crash audit)
    completed_nodes: Annotated[list[str], operator.add]
    # running | awaiting_approval | published | changes_requested | failed
    status: str
    error: str | None
    # free-form per-run metadata (kept small; no document payloads)
    meta: dict[str, Any]
