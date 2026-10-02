"""C3: hard gates deterministas sobre las 4 capas LLM.

Cada gate es una funcion pura ``f(case) -> {"gate", "passed", "details"}`` que
delega el trabajo en ``deterministic_judge``: aqui no hay ningun calculo, solo
la politica de "que puerta existe y como se lee su veredicto".

Fijo del repo: **nada de LLM juzgando a LLM**. No hay embeddings, no hay
proveedor, no hay red. Un caso declara en ``applies_to`` que puertas ejercita;
una puerta declarada en ``NON_SKIPPABLE_GATES`` que no encuentra su clave de
``expected`` FALLA con "...: el gate no puede omitirse", porque su unico trabajo
es detectar una ausencia y una ausencia silenciosa lo dejaria verde.

Dos puertas son de nivel dataset (``layers_all_covered`` y
``negative_controls_present``): el runner les pasa el sobre
``{"id": "dataset", "dataset": {...}}`` para que la firma ``f(case)`` siga
siendo uniforme y testeable una por una.
"""

from __future__ import annotations

from typing import Any

from evals.llm.deterministic_judge import (
    LAYERS,
    check_abstention,
    check_claims_evidence,
    check_confidences,
    check_degraded_honesty,
    check_grounding,
    check_labels,
    check_probabilities,
    check_scenario_ordering,
    check_verdict_allowed,
    parse_output,
)

MIN_CASES = 40
MIN_CASES_PER_LAYER = 10
MIN_NEGATIVE_CONTROLS = 6

# Puertas cuyo unico valor es atrapar una ausencia. Si el caso no declara la
# clave que las activa, pasan en verde sin haber mirado nada.
NON_SKIPPABLE_GATES = frozenset({
    "provider_failure_is_degraded_not_answered",
    "abstained_when_insufficient",
})


def _result(gate: str, passed: bool, details: list[str]) -> dict[str, Any]:
    return {"gate": gate, "passed": passed, "details": details}


def gate_output_schema_valid(case: dict) -> dict[str, Any]:
    """Objetivo 1 del judge: la salida parsea contra el contrato de la capa.

    La ausencia de `model_output` no se perdona (el gate devuelve el problema
    "falta model_output: el gate no puede omitirse"), pero una `null` DECLARADA
    con su `provider` si es una forma de fallo legitima: no hay nada que parsear
    y de eso se ocupa `provider_failure_is_degraded_not_answered`.
    """
    problems = list(parse_output(case).problems)
    return _result("output_schema_valid", not problems, problems)


def gate_no_unknown_labels(case: dict) -> dict[str, Any]:
    """Etiqueta desconocida = no lo se, jamas una respuesta."""
    return _result("no_unknown_labels", not check_labels(case), check_labels(case))


def gate_confidence_in_range(case: dict) -> dict[str, Any]:
    problems = check_confidences(case)
    return _result("confidence_in_range", not problems, problems)


def gate_no_hallucinated_numbers(case: dict) -> dict[str, Any]:
    problems = check_grounding(case)
    return _result("no_hallucinated_numbers", not problems, problems)


def gate_claims_have_evidence(case: dict) -> dict[str, Any]:
    problems = check_claims_evidence(case)
    return _result("claims_have_evidence", not problems, problems)


def gate_debate_verdict_allowed(case: dict) -> dict[str, Any]:
    problems = check_verdict_allowed(case)
    return _result("debate_verdict_allowed", not problems, problems)


def gate_scenario_ordering(case: dict) -> dict[str, Any]:
    problems = check_scenario_ordering(case)
    return _result("scenario_ordering", not problems, problems)


def gate_probabilities_sum_to_one(case: dict) -> dict[str, Any]:
    problems = check_probabilities(case)
    return _result("probabilities_sum_to_one", not problems, problems)


def gate_provider_failure_is_degraded_not_answered(case: dict) -> dict[str, Any]:
    """No OMITIBLE: `expected.degraded` ausente = puerta anulada, no verde."""
    problems = check_degraded_honesty(case)
    return _result(
        "provider_failure_is_degraded_not_answered", not problems, problems
    )


def gate_abstained_when_insufficient(case: dict) -> dict[str, Any]:
    """No OMITIBLE: `expected.abstain` ausente = puerta anulada, no verde."""
    problems = check_abstention(case)
    return _result("abstained_when_insufficient", not problems, problems)


def _dataset(case: dict) -> dict[str, Any]:
    dataset = case.get("dataset")
    return dataset if isinstance(dataset, dict) else {}


def gate_layers_all_covered(case: dict) -> dict[str, Any]:
    """Cobertura del dataset: las 4 capas con al menos 10 casos cada una."""
    cases = _dataset(case).get("cases") or []
    per_layer: dict[str, int] = dict.fromkeys(LAYERS, 0)
    for item in cases:
        layer = item.get("layer") if isinstance(item, dict) else None
        if layer in per_layer:
            per_layer[layer] += 1
    details: list[str] = []
    if len(cases) < MIN_CASES:
        details.append(f"{len(cases)} casos < {MIN_CASES}")
    for layer in LAYERS:
        if per_layer[layer] < MIN_CASES_PER_LAYER:
            details.append(f"{layer}: {per_layer[layer]} casos < {MIN_CASES_PER_LAYER}")
    unknown = {
        item.get("layer")
        for item in cases
        if isinstance(item, dict) and item.get("layer") not in LAYERS
    }
    if unknown:
        details.append(f"capas declaradas fuera del contrato: {sorted(map(str, unknown))}")
    return _result("layers_all_covered", not details, details)


def gate_negative_controls_present(case: dict) -> dict[str, Any]:
    """Sin controles negativos los gates podrian estar todos muertos."""
    cases = _dataset(case).get("cases") or []
    negatives = [
        item
        for item in cases
        if isinstance(item, dict) and item.get("expect_gate_failure")
    ]
    details = []
    if len(negatives) < MIN_NEGATIVE_CONTROLS:
        details.append(f"{len(negatives)} controles negativos < {MIN_NEGATIVE_CONTROLS}")
    per_gate: dict[str, int] = {}
    for item in negatives:
        name = str(item.get("expect_gate_failure"))
        per_gate[name] = per_gate.get(name, 0) + 1
    if len(per_gate) < 4:
        details.append(f"solo {len(per_gate)} puertas con control negativo < 4")
    return _result("negative_controls_present", not details, details)


GATES = {
    "output_schema_valid": gate_output_schema_valid,
    "no_unknown_labels": gate_no_unknown_labels,
    "confidence_in_range": gate_confidence_in_range,
    "no_hallucinated_numbers": gate_no_hallucinated_numbers,
    "claims_have_evidence": gate_claims_have_evidence,
    "debate_verdict_allowed": gate_debate_verdict_allowed,
    "scenario_ordering": gate_scenario_ordering,
    "probabilities_sum_to_one": gate_probabilities_sum_to_one,
    "provider_failure_is_degraded_not_answered": (
        gate_provider_failure_is_degraded_not_answered
    ),
    "abstained_when_insufficient": gate_abstained_when_insufficient,
    "layers_all_covered": gate_layers_all_covered,
    "negative_controls_present": gate_negative_controls_present,
}

# Las puertas de nivel dataset no se declaran en el `applies_to` de cada caso.
DATASET_GATES = ("layers_all_covered", "negative_controls_present")


def run_case(case: dict) -> list[dict[str, Any]]:
    return [gate(case) for gate in GATES.values()]