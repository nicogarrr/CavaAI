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
    # node name -> real artifact reference (never a pending stand-in, never
    # document contents): "company:<id>", "sha256:<hex>", "evidence:facts=N,...",
    # "model:v3:<fp>", "valuation:<id>", "thesis:v2:draft:sections=3:sha=<hex>",
    # "audit:facts={...}|docs={...}|lowconf=N", "redteam:<id>:score=N",
    # "candidate:sha256:<hex>", "approval:<decision>",
    # "thesis_published:v<n>" | "thesis_unpublished:v<n>:<status>" | "thesis:none"
    artifacts: dict[str, str]
    # append-only log of nodes that committed their artifact (crash audit)
    completed_nodes: Annotated[list[str], operator.add]
    # running | awaiting_approval | approved | published | changes_requested | failed.
    # "approved" and "published" are different claims: a human approval never
    # asserts a publication the classic path did not perform.
    status: str
    error: str | None
    # free-form per-run metadata (kept small; no document payloads)
    meta: dict[str, Any]
