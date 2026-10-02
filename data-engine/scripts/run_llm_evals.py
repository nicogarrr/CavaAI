"""C3: ejecuta el dataset congelado de las 4 capas LLM contra los gates.

Uso: python data-engine/scripts/run_llm_evals.py [--json]

Mismo contrato que ``scripts/run_offline_evals.py``: ``applies_to`` como opt-out
explicito, ``expect_gate_failure`` para los controles negativos, cobertura
impresa por puerta y por capa, y FALLO (exit 1) si una puerta o una capa corrio
0 veces. La diferencia es que aqui la corrida entera va dentro del guardian de
red del judge: no hay proveedor al que llamar aunque alguien lo intente.

Determinista: sin red, sin LLM, sin embeddings. ``--json`` imprime el informe
maquina a maquina para CI.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evals.llm.deterministic_judge import LAYERS, no_network  # noqa: E402
from evals.llm.llm_gates import DATASET_GATES, GATES  # noqa: E402

DATASET_PATH = ROOT / "evals" / "llm" / "llm_layers_v1.json"


def _applies(case: dict, gate_name: str) -> bool:
    """Igual que el runner offline: sin `applies_to` el gate corre."""
    declared = case.get("applies_to")
    if declared is None:
        return True
    return gate_name in declared


def _dataset_case(dataset: dict) -> dict:
    """Sobre homogeneo para las puertas de nivel dataset."""
    return {"id": "dataset", "dataset": dataset}


def run(dataset: dict) -> dict:
    """Ejecuta todo y devuelve el informe; el exit code lo decide `main`."""
    per_case_gates = dict.fromkeys(GATES, 0)
    executed = dict.fromkeys(GATES, 0)
    per_layer = dict.fromkeys(LAYERS, 0)
    per_category: dict[str, int] = {}
    per_layer_executed: dict[str, dict[str, int]] = {
        layer: dict.fromkeys(GATES, 0) for layer in LAYERS
    }
    failures: list[str] = []
    total = 0
    cases = dataset.get("cases") or []
    for case in cases:
        layer = str(case.get("layer"))
        per_layer[layer] = per_layer.get(layer, 0) + 1
        category = str(case.get("category"))
        per_category[category] = per_category.get(category, 0) + 1
        expected_failure = case.get("expect_gate_failure")
        failed_gates: list[str] = []
        for gate_name, gate in GATES.items():
            if gate_name in DATASET_GATES:
                continue
            if not _applies(case, gate_name):
                continue
            result = gate(case)
            total += 1
            executed[gate_name] += 1
            per_case_gates[gate_name] += 1
            per_layer_executed.setdefault(layer, {})
            per_layer_executed[layer][gate_name] = (
                per_layer_executed[layer].get(gate_name, 0) + 1
            )
            if expected_failure == gate_name:
                if result["passed"]:
                    failures.append(f"{case['id']}: {gate_name} debia FALLAR y paso")
                else:
                    failed_gates.append(gate_name)
            elif not result["passed"]:
                failed_gates.append(gate_name)
                failures.append(
                    f"{case['id']}: {gate_name} fallo: {'; '.join(result['details'])}"
                )
        case["_failed_gates"] = failed_gates

    # Puertas de nivel dataset: una ejecucion cada una sobre el sobre.
    envelope = _dataset_case(dataset)
    dataset_results: list[dict] = []
    for gate_name in DATASET_GATES:
        result = GATES[gate_name](envelope)
        executed[gate_name] += 1
        dataset_results.append(result)
        if not result["passed"]:
            failures.append(f"{gate_name} fallo: {'; '.join(result['details'])}")

    # Una puerta o una capa que nunca corrio no es una puerta o capa que pasa.
    never_ran = sorted(name for name, count in executed.items() if count == 0)
    if never_ran:
        failures.append(
            "gates que nunca se ejecutaron sobre ningun caso: " + ", ".join(never_ran)
        )
    uncovered_layers = sorted(
        layer for layer, count in per_layer.items() if count == 0 or layer not in LAYERS
    )
    if uncovered_layers:
        failures.append("capas sin ningun caso: " + ", ".join(uncovered_layers))

    return {
        "total_checks": total,
        "cases": len(cases),
        "failures": failures,
        "executed": executed,
        "per_layer": per_layer,
        "per_category": per_category,
        # Informativo, no bloqueante: una puerta que solo aplica a una capa
        # (debate_verdict_allowed) tiene que quedar sin ejercitar en las otras.
        "unused_gate_per_layer": sorted(
            f"{layer}/{name}"
            for layer, counts in per_layer_executed.items()
            for name, count in counts.items()
            if count == 0 and name not in DATASET_GATES
        ),
        "dataset_results": dataset_results,
    }


def _print_report(dataset: dict, report: dict) -> None:
    for case in dataset.get("cases") or []:
        failed = case.get("_failed_gates") or []
        status = "FAIL" if failed else "ok"
        extra = f" -> {', '.join(failed)}" if failed else ""
        print(f"[{status}] {case['id']} ({case['layer']}/{case['category']}){extra}")
    print(f"\n{report['cases']} casos -> {report['total_checks']} checks ejecutados")
    print("Cobertura por gate:")
    for name, count in report["executed"].items():
        marker = "  <-- NUNCA SE EJECUTO" if count == 0 else ""
        print(f"  {name}: {count}{marker}")
    print("Cobertura por capa:")
    for layer, count in sorted(report["per_layer"].items()):
        marker = "  <-- SIN CASOS" if count == 0 else ""
        print(f"  {layer}: {count}{marker}")
    print("Cobertura por categoria:")
    for category, count in sorted(report["per_category"].items()):
        print(f"  {category}: {count}")
    if report["unused_gate_per_layer"]:
        print("Puertas sin ejercitar por capa (informativo):")
        for name in report["unused_gate_per_layer"]:
            print(f"  {name}")
    if report["failures"]:
        print(f"\n{len(report['failures'])} FALLOS:")
        for failure in report["failures"]:
            print(f"  - {failure}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="informe JSON para CI")
    args = parser.parse_args(argv)
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    with no_network():
        report = run(dataset)
    if args.json:
        payload = {
            "dataset": dataset.get("dataset"),
            **{k: v for k, v in report.items() if k != "dataset_results"},
            "dataset_results": report["dataset_results"],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_report(dataset, report)
    if report["failures"]:
        if not args.json:
            print("\nRevisa los fallos anteriores.")
        return 1
    if not args.json:
        print("\nTodos los gates en verde.")
    return 0


if __name__ == "__main__":
    sys.exit(main())