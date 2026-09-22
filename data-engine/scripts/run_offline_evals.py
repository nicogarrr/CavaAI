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


def main() -> int:
    dataset_path = ROOT / "evals" / "thesis_quality_v1.json"
    dataset = json.loads(dataset_path.read_text())
    failures: list[str] = []
    total = 0
    for case in dataset["cases"]:
        expected_failure = case.get("expect_gate_failure")
        for gate_name, gate in GATES.items():
            result = gate(case)
            total += 1
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
    print(f"\n{len(dataset['cases'])} casos x {len(GATES)} gates = {total} checks")
    if failures:
        print(f"{len(failures)} FALLOS:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("Todos los gates en verde.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
