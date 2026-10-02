"""Ejecuta el dataset congelado del backtest point-in-time contra los hard gates.

Uso: python data-engine/scripts/run_backtest_evals.py [--json]

Mismo contrato que ``scripts/run_offline_evals.py`` (del que se copia la
semantica de ``applies_to`` y ``expect_gate_failure``), y por las mismas razones:
una puerta que no se ejercita no es una puerta verde, es una puerta muerta.

- ``applies_to`` absent = la puerta corre; el dataset opta OUT explicitamente.
- ``expect_gate_failure`` = esta puerta DEBE fallar en este caso.
- Al final se imprime la cobertura por puerta y se falla si alguna corrio 0 veces.
- Exit 1 ante cualquier discrepancia. ``--json`` vuelca el resultado para CI.

Determinista, sin red, sin LLM, sin base de datos: lee el JSON congelado que
produjo ``scripts/build_backtest_eval_dataset.py``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evals.backtest.backtest_gates import GATES, NON_SKIPPABLE_GATES  # noqa: E402

DATASET = ROOT / "evals" / "backtest" / "backtest_v1.json"


def _applies(case: dict, gate_name: str) -> bool:
    """Whether a case declares that it exercises a gate.

    Same contract as the thesis gates: no declaration means the gate runs, and a
    dataset must opt OUT explicitly. A gate that quietly stopped exercising
    anything would otherwise read as a gate that passed.
    """
    declared = case.get("applies_to")
    if declared is None:
        return True
    return gate_name in declared


def run(dataset_path: Path = DATASET) -> dict:
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    executed: dict[str, int] = dict.fromkeys(GATES, 0)
    total = 0
    per_case: list[dict] = []

    for case in dataset["cases"]:
        expected_failure = case.get("expect_gate_failure")
        case_failures: list[str] = []
        for gate_name, gate in GATES.items():
            if not _applies(case, gate_name):
                continue
            result = gate(case)
            total += 1
            executed[gate_name] += 1
            if expected_failure == gate_name:
                if result["passed"]:
                    message = f"{case['id']}: {gate_name} debia FALLAR y paso"
                    failures.append(message)
                    case_failures.append(message)
            elif not result["passed"]:
                message = (
                    f"{case['id']}: {gate_name} fallo: {'; '.join(result['details'])}"
                )
                failures.append(message)
                case_failures.append(message)
        per_case.append(
            {
                "id": case["id"],
                "category": case["category"],
                "note": case.get("note"),
                "as_of": case.get("as_of"),
                "expect_gate_failure": expected_failure,
                "failures": case_failures,
            }
        )

    never_ran = sorted(name for name, count in executed.items() if count == 0)
    if never_ran:
        failures.append(
            "gates que nunca se ejecutaron sobre ningun caso: " + ", ".join(never_ran)
        )

    thin = sorted(
        (name, count)
        for name, count in executed.items()
        if 0 < count < 2 and name not in NON_SKIPPABLE_GATES
    )
    for name, count in thin:
        failures.append(f"gate {name} solo se ejercito {count} vez: cobertura insuficiente")

    return {
        "dataset": dataset_path.name,
        "version": dataset.get("version"),
        "cases": len(dataset["cases"]),
        "checks": total,
        "coverage": executed,
        "non_skippable": list(NON_SKIPPABLE_GATES),
        "negative_controls": sum(1 for case in dataset["cases"] if case.get("expect_gate_failure")),
        "failures": failures,
        "ok": not failures,
        "per_case": per_case,
    }


def _print_human(result: dict) -> None:
    for case in result["per_case"]:
        status = "FAIL" if case["failures"] else "ok"
        expected = case["expect_gate_failure"]
        suffix = f" [debe fallar: {expected}]" if expected else ""
        print(f"[{status}] {case['id']} ({case['category']}, as_of={case['as_of']}){suffix}")

    print(f"\n{result['cases']} casos -> {result['checks']} checks ejecutados")
    print(f"Controles negativos: {result['negative_controls']}")
    print("Cobertura por gate:")
    for name, count in result["coverage"].items():
        marker = "  <-- NUNCA SE EJECUTO" if count == 0 else ""
        non_skippable = " [no omitible]" if name in result["non_skippable"] else ""
        print(f"  {name}: {count}{non_skippable}{marker}")

    if result["failures"]:
        print(f"\n{len(result['failures'])} FALLOS:")
        for failure in result["failures"]:
            print(f"  - {failure}")
        return
    print("\nTodos los gates en verde.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="salida JSON para CI")
    parser.add_argument(
        "--dataset",
        default=None,
        help=(
            "Dataset alterno. Existe para que los tests puedan comprobar que el "
            "runner SABE fallar, mutilando una copia en vez de tocar el real."
        ),
    )
    args = parser.parse_args()

    result = run(Path(args.dataset) if args.dataset else DATASET)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        _print_human(result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
