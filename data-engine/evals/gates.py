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


_DECIMAL_COMMA = re.compile(r"^[-+]?\d+,\d{1,2}$")


def _norm_number(text: str) -> float | None:
    """Parse a number written either way round.

    Stripping every comma turned "1,2" (one point two) into 12.0, so a
    hallucinated magnitude could pass the invented-numbers gate through the back
    door of normalisation. A comma followed by exactly one or two digits is a
    decimal separator; any other comma is a thousands separator.
    """
    raw = str(text).strip().rstrip(".")
    if not raw:
        return None
    if "," in raw and "." in raw:
        # Written in one of the two conventions; the LAST separator is decimal.
        raw = (
            raw.replace(",", "")
            if raw.rindex(".") > raw.rindex(",")
            else raw.replace(".", "").replace(",", ".")
        )
    elif _DECIMAL_COMMA.match(raw):
        raw = raw.replace(",", ".")
    else:
        raw = raw.replace(",", "")
    try:
        return float(raw)
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
        # Omitting the key must NOT pass: the gate exists to catch exactly the
        # case where the probabilities are missing or wrong.
        return _result(
            "probabilities_sum_to_one",
            False,
            ["el artefacto no trae scenario_probabilities: el gate no puede omitirse"],
        )
    total = sum(float(v) for v in scenarios.values() if v is not None)
    passed = abs(total - 1.0) <= 0.01
    return _result(
        "probabilities_sum_to_one",
        passed,
        [f"suma={total:.4f} (esperado 1.0 +/- 0.01)"],
    )


def _frozen_by_metric(case: dict) -> dict[str, set[float]]:
    out: dict[str, set[float]] = {}
    for metric, value in (case.get("frozen_facts") or {}).items():
        number = _norm_number(str(value))
        if number is not None:
            out.setdefault(metric, set()).add(number)
    return out


def _section_text(section: dict) -> str:
    """The dataset stores section prose under "content"; the API uses "body"."""
    if not isinstance(section, dict):
        return str(section or "")
    return str(section.get("body") or section.get("content") or "")


def _texts_to_check(artifact: dict) -> list[tuple[str, str, str | None]]:
    """Every piece of model-authored prose, with the metric it claims to be about.

    The gate used to read only `artifact["claims"]`, so the sections the model
    writes - the text the user actually reads - were never checked at all.
    """
    rows: list[tuple[str, str, str | None]] = [
        ("claim", str(c.get("text") or ""), c.get("metric"))
        for c in artifact.get("claims", [])
        if isinstance(c, dict) and c.get("material", True)
    ]
    rows += [
        ("section", _section_text(s), s.get("metric") if isinstance(s, dict) else None)
        for s in artifact.get("sections", [])
    ]
    return [(kind, text, metric) for kind, text, metric in rows if text]


def gate_no_invented_numbers(case: dict) -> dict:
    """Every number must come from a frozen fact of the SAME metric."""
    artifact = case.get("artifact") or {}
    by_metric = _frozen_by_metric(case)
    known = set().union(*by_metric.values()) if by_metric else set()
    problems: list[str] = []
    for kind, text, metric in _texts_to_check(artifact):
        # When the text declares a metric, only that metric's facts can vouch for
        # it; otherwise any frozen fact may.
        pool = by_metric.get(metric, set()) if metric else known
        for match in _NUMBER_RE.findall(text):
            number = _norm_number(match)
            if number is None or _is_tolerance_value(number):
                continue
            if number not in pool:
                label = f" para {metric!r}" if metric else ""
                problems.append(f"numero sin frozen fact{label} en {kind}: {match}")
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
    for section in artifact.get("sections", []):
        if not isinstance(section, dict):
            continue
        # A section that carries a number and cites nothing is the same defect as
        # an unsourced material claim, and the user reads the section.
        cited = section.get("citations") or section.get("evidence_ids") or []
        if cited and not any(cid in evidence_ids for cid in cited):
            problems.append(
                f"seccion con citas sin evidencia: {section.get('key')} "
                f"{_section_text(section)[:60]}"
            )
    return _result("material_claims_have_evidence", not problems, problems[:10])


def gate_valuation_unchanged_by_prompt_edits(case: dict) -> dict:
    """La valoracion es determinista: el hash congelado no puede cambiar."""
    artifact = case.get("artifact") or {}
    expected = (case.get("expected") or {}).get("valuation_hash")
    actual = artifact.get("valuation_hash")
    if expected is None or actual is None:
        # A missing hash used to pass, so a run that moved the DCF could silence
        # this gate simply by not publishing the hash.
        return _result(
            "valuation_unchanged",
            False,
            ["falta valuation_hash en expected o artifact: el gate no puede omitirse"],
        )
    return _result(
        "valuation_unchanged",
        actual == expected,
        [f"hash {actual} != {expected}"],
    )


def gate_replay_no_duplicate_version(case: dict) -> dict:
    versions = (case.get("artifact") or {}).get("versions")
    if not versions:
        return _result(
            "replay_no_duplicate_version",
            False,
            ["el artefacto no trae versions: el gate no puede omitirse"],
        )
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
