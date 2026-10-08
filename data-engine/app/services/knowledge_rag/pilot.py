"""Metricas del piloto: recall del pasaje esperado y precision de cita.

Un caso declara el pasaje esperado como fragmento literal (``expected_quote``)
y la fuente (``expected_source_sha256`` o ``expected_title``). Un resultado
"acierta" si alguna cita top-k de esa fuente contiene el fragmento (tras
normalizar espacios). Es determinista: no hay LLM juez.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.knowledge_rag.domain import normalize_ws


@dataclass
class PilotCase:
    id: str
    question: str
    expected_quote: str | None  # None => debe abstenerse
    expected_source_sha256: str | None = None
    expected_title: str | None = None
    filters: dict[str, Any] | None = None


def _hit(case: PilotCase, citation: dict[str, Any], k: int) -> bool:
    if case.expected_quote is None or citation["number"] > k:
        return False
    if case.expected_source_sha256 and citation["source_sha256"] != case.expected_source_sha256:
        return False
    if case.expected_title and citation["title"] != case.expected_title:
        return False
    haystack = normalize_ws(citation.get("context") or citation["quote"]).lower()
    return normalize_ws(case.expected_quote).lower() in haystack


def score_pilot(
    cases: list[PilotCase], responses: dict[str, list[dict[str, Any]]], ks: tuple[int, ...] = (1, 3, 6)
) -> dict[str, Any]:
    """``responses``: case id -> lista de citas (dict de ``Citation.public``)."""
    answerable = [c for c in cases if c.expected_quote is not None]
    unanswerable = [c for c in cases if c.expected_quote is None]
    recall = {
        f"recall@{k}": (
            sum(any(_hit(c, cit, k) for cit in responses.get(c.id, [])) for c in answerable) / len(answerable)
            if answerable
            else None
        )
        for k in ks
    }
    cites = [(c, cit) for c in answerable for cit in responses.get(c.id, [])]
    verified = sum(1 for _c, cit in cites if cit.get("verified"))
    relevant = sum(1 for c, cit in cites if _hit(c, cit, 10**6))
    return {
        "cases": len(cases),
        "answerable": len(answerable),
        "unanswerable": len(unanswerable),
        **recall,
        "citation_verifiable_rate": verified / len(cites) if cites else None,
        "citation_precision": relevant / len(cites) if cites else None,
        "abstention_rate": (
            sum(1 for c in unanswerable if not responses.get(c.id)) / len(unanswerable)
            if unanswerable
            else None
        ),
    }
