"""D3: ejecuta el dataset congelado de retornos realizados contra los hard gates.

Uso: python data-engine/scripts/run_realized_evals.py [--json]

Mismo contrato que ``scripts/run_offline_evals.py``: ``applies_to`` declara qué
gates ejercita cada caso (opt-out explícito), ``expect_gate_failure`` marca los
controles negativos, se imprime la cobertura por puerta y **una puerta que
corrió cero veces es un fallo**, no un verde. Los gates de
``NON_SKIPPABLE_GATES`` se ejecutan siempre: no hay forma de apagarlos desde el
dataset. Determinista: sin red, sin LLM, sin base de datos.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evals.realized.realized_gates import GATES, NON_SKIPPABLE_GATES  # noqa: E402

DATASET = ROOT / "evals" / "realized" / "realized_v1.json"


def _applies(case: dict, gate_name: str) -> bool:
    """Un dataset se puede apartar de una puerta; las NO OMITIBLES no."""
    if gate_name in NON_SKIPPABLE_GATES:
        return True
    declared = case.get("applies_to")
    if declared is None:
        return True
    return gate_name in declared


def evaluate(dataset: dict) -> dict:
    failures: list[str] = []
    executed: dict[str, int] = dict.fromkeys(GATES, 0)
    total = 0
    rows: list[dict] = []
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
                    case_failures.append(
                        f"{case['id']}: {gate_name} debia FALLAR y paso"
                    )
            elif not result["passed"]:
                case_failures.append(
                    f"{case['id']}: {gate_name} fallo: {'; '.join(result['details'])}"
                )
        failures.extend(case_failures)
        rows.append(
            {
                "id": case["id"],
                "category": case.get("category"),
                "status": "FAIL" if case_failures else "ok",
                "negative_control": expected_failure,
                "failures": case_failures,
            }
        )
    never_ran = sorted(name for name, count in executed.items() if count == 0)
    if never_ran:
        failures.append(
            "gates que nunca se ejecutaron sobre ningun caso: " + ", ".join(never_ran)
        )
    return {
        "dataset": dataset.get("dataset"),
        "cases": len(dataset["cases"]),
        "checks": total,
        "executed": executed,
        "never_ran": never_ran,
        "failures": failures,
        "rows": rows,
        "passed": not failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json", action="store_true", help="imprime el informe completo en JSON"
    )
    args = parser.parse_args(argv)

    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    report = evaluate(dataset)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1 if report["failures"] else 0

    for row in report["rows"]:
        marker = " [control negativo]" if row["negative_control"] else ""
        print(f"[{row['status']}] {row['id']} ({row['category']}){marker}")
    print(
        f"\n{report['cases']} casos -> {report['checks']} checks ejecutados "
        f"({sum(1 for r in report['rows'] if r['negative_control'])} controles negativos)"
    )
    print("Cobertura por gate:")
    for name, count in report["executed"].items():
        marker = "  <-- NUNCA SE EJECUTO" if count == 0 else ""
        if name in NON_SKIPPABLE_GATES:
            marker += "  (no omitible)"
        print(f"  {name}: {count}{marker}")
    if report["failures"]:
        print(f"\n{len(report['failures'])} FALLOS:")
        for failure in report["failures"]:
            print(f"  - {failure}")
        return 1
    print("\nTodos los gates en verde.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
