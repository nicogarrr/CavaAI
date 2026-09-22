"""Stage 5: hard gates deterministicos para evaluacion offline de tesis.

Cada gate es una funcion pura sobre un "artifact" (dict con la forma de
una tesis congelada) y los "frozen_facts" del caso. Nada de LLM juzgando
a LLM: JSON/schema, numeros contra hechos congelados, enlaces de
evidencia, suma de probabilidades, replay sin duplicados. Un gate
devuelve {"gate", "passed", "details"}.
"""

from __future__ import annotations

import re
from typing import Any

REQUIRED_ARTIFACT_KEYS = {
    "ticker": str,
    "status": str,
    "sections": list,
    "claims": list,
    "evidence": list,
}

_NUMBER_RE = re.compile(r"-?\d[\d.,]*")


def _norm_number(text: str) -> float | None:
    try:
        return float(text.replace(",", "").rstrip("."))
    except ValueError:
        return None


def gate_schema_valid(case: dict) -> dict:
    artifact = case.get("artifact") or {}
    problems: list[str] = []
    for key, expected_type in REQUIRED_ARTIFACT_KEYS.items():
        if key not in artifact:
            problems.append(f"falta {key}")
        elif not isinstance(artifact[key], expected_type):
            problems.append(f"{key} no es {expected_type.__name__}")
    scenarios = artifact.get("scenario_probabilities")
    if scenarios is not None and not isinstance(scenarios, dict):
        problems.append("scenario_probabilities no es dict")
    status = artifact.get("status")
    if status is not None and status not in {"draft", "approved", "published", "changes_requested"}:
        problems.append(f"status desconocido: {status}")
    return _result("schema_valid", not problems, problems)


def gate_probabilities_sum_to_one(case: dict) -> dict:
    scenarios = (case.get("artifact") or {}).get("scenario_probabilities")
    if not scenarios:
        return _result("probabilities_sum_to_one", True, ["sin escenarios: no aplica"])
    total = sum(float(v) for v in scenarios.values() if v is not None)
    passed = abs(total - 1.0) <= 0.01
    return _result(
        "probabilities_sum_to_one",
        passed,
        [f"suma={total:.4f} (esperado 1.0 +/- 0.01)"],
    )


def gate_no_invented_numbers(case: dict) -> dict:
    """Todo numero de un claim material debe existir en los frozen facts."""
    artifact = case.get("artifact") or {}
    frozen_numbers = set()
    for value in (case.get("frozen_facts") or {}).values():
        number = _norm_number(str(value))
        if number is not None:
            frozen_numbers.add(number)
    problems: list[str] = []
    for claim in artifact.get("claims", []):
        if not claim.get("material", True):
            continue
        for match in _NUMBER_RE.findall(claim.get("text", "")):
            number = _norm_number(match)
            if number is None:
                continue
            if number not in frozen_numbers and not _is_tolerance_value(number):
                problems.append(f"numero inventado en claim: {match}")
    return _result("no_invented_numbers", not problems, problems[:10])


def _is_tolerance_value(number: float) -> bool:
    """Indices/pequenos ordinales no son hechos financieros."""
    return number in {0, 1, 2, 3}


def gate_material_claims_have_evidence(case: dict) -> dict:
    artifact = case.get("artifact") or {}
    evidence_ids = {e.get("id") for e in artifact.get("evidence", [])}
    problems = []
    for claim in artifact.get("claims", []):
        if not claim.get("material", True):
            continue
        linked = [eid for eid in claim.get("evidence_ids", []) if eid in evidence_ids]
        if not linked:
            problems.append(f"claim sin evidencia: {claim.get('text', '')[:60]}")
    return _result("material_claims_have_evidence", not problems, problems[:10])


def gate_valuation_unchanged_by_prompt_edits(case: dict) -> dict:
    """La valoracion es determinista: el hash congelado no puede cambiar."""
    artifact = case.get("artifact") or {}
    expected = (case.get("expected") or {}).get("valuation_hash")
    actual = artifact.get("valuation_hash")
    if expected is None or actual is None:
        return _result("valuation_unchanged", True, ["sin hash: no aplica"])
    return _result(
        "valuation_unchanged",
        actual == expected,
        [f"hash {actual} != {expected}"],
    )


def gate_replay_no_duplicate_version(case: dict) -> dict:
    versions = (case.get("artifact") or {}).get("versions")
    if not versions:
        return _result("replay_no_duplicate_version", True, ["sin replay: no aplica"])
    duplicates = len(versions) - len(set(versions))
    return _result(
        "replay_no_duplicate_version",
        duplicates == 0,
        [f"{duplicates} versiones duplicadas"] if duplicates else [],
    )


def gate_expected_status(case: dict) -> dict:
    """El comportamiento esperado del caso (p.ej. rechazar fair value)."""
    artifact = case.get("artifact") or {}
    expected = case.get("expected") or {}
    problems = []
    if "status" in expected and artifact.get("status") != expected["status"]:
        problems.append(f"status {artifact.get('status')} != {expected['status']}")
    if expected.get("fair_value") == "absent" and artifact.get("fair_value") is not None:
        problems.append("fair_value presente pero debia estar ausente")
    if expected.get("fair_value") == "present" and artifact.get("fair_value") is None:
        problems.append("fair_value ausente pero debia existir")
    allowed = expected.get("debate_verdict_in")
    if allowed and artifact.get("debate_verdict") not in allowed:
        problems.append(
            f"veredicto {artifact.get('debate_verdict')} fuera de {allowed}"
        )
    return _result("expected_status", not problems, problems)


GATES = {
    "schema_valid": gate_schema_valid,
    "probabilities_sum_to_one": gate_probabilities_sum_to_one,
    "no_invented_numbers": gate_no_invented_numbers,
    "material_claims_have_evidence": gate_material_claims_have_evidence,
    "valuation_unchanged": gate_valuation_unchanged_by_prompt_edits,
    "replay_no_duplicate_version": gate_replay_no_duplicate_version,
    "expected_status": gate_expected_status,
}


def run_case(case: dict) -> list[dict]:
    return [gate(case) for gate in GATES.values()]


def _result(gate: str, passed: bool, details: list[str]) -> dict:
    return {"gate": gate, "passed": passed, "details": details}
