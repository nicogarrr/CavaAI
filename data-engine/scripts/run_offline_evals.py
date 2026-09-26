"""Stage 5: ejecuta el dataset congelado de tesis contra los hard gates.

Uso: python data-engine/scripts/run_offline_evals.py
Exit 1 si algun caso falla un gate que debia pasar (o pasa uno que debia
fallar). Determinista: sin red, sin LLM.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evals.gates import GATES  # noqa: E402


def _applies(case: dict, gate_name: str) -> bool:
    """Whether a case declares that it exercises a gate.

    A gate that a case does not claim is SKIPPED, and that is recorded: three of
    the gates used to return `passed=True` with "no aplica" when their key was
    absent, so omitting `valuation_hash` was enough to silence the gate that
    exists to catch a moved DCF. Now applicability is declared up front and the
    runner reports how many cases actually executed each gate, so a gate that
    stops exercising anything is visible instead of green.
    """
    declared = case.get("applies_to")
    if declared is None:
        # No declaration: the gate runs. A dataset must opt OUT explicitly.
        return True
    return gate_name in declared


def main() -> int:
    dataset_path = ROOT / "evals" / "thesis_quality_v1.json"
    dataset = json.loads(dataset_path.read_text())
    failures: list[str] = []
    executed: dict[str, int] = dict.fromkeys(GATES, 0)
    total = 0
    for case in dataset["cases"]:
        expected_failure = case.get("expect_gate_failure")
        for gate_name, gate in GATES.items():
            if not _applies(case, gate_name):
                continue
            result = gate(case)
            total += 1
            executed[gate_name] += 1
            if expected_failure == gate_name:
                if result["passed"]:
                    failures.append(
                        f"{case['id']}: {gate_name} debia FALLAR y paso"
                    )
            elif not result["passed"]:
                failures.append(
                    f"{case['id']}: {gate_name} fallo: {'; '.join(result['details'])}"
                )
        status = "FAIL" if any(f.startswith(case["id"] + ":") for f in failures) else "ok"
        print(f"[{status}] {case['id']} ({case['category']})")

    print(f"\n{len(dataset['cases'])} casos -> {total} checks ejecutados")
    print("Cobertura por gate:")
    for gate_name, count in executed.items():
        marker = "  <-- NUNCA SE EJECUTO" if count == 0 else ""
        print(f"  {gate_name}: {count}{marker}")

    # A gate that never ran is not a passing gate.
    never_ran = [name for name, count in executed.items() if count == 0]
    if never_ran:
        failures.append(
            "gates que nunca se ejecutaron sobre ningun caso: " + ", ".join(sorted(never_ran))
        )

    if failures:
        print(f"\n{len(failures)} FALLOS:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("\nTodos los gates en verde.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
