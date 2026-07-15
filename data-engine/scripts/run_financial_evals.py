from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.metric_semantics import MetricSemanticsRegistry


def main() -> None:
    path = ROOT / "evals" / "financial_engine_v1.json"
    cases = json.loads(path.read_text(encoding="utf-8"))
    failures = []
    for case in cases:
        status, _ = MetricSemanticsRegistry.classify(
            case["metric"], Decimal(case["expected"]), Decimal(case["actual"])
        )
        if status != case["status"]:
            failures.append({**case, "actual_status": status})
    if failures:
        raise SystemExit(f"Financial eval failures: {json.dumps(failures)}")
    print(f"Financial evals passed: {len(cases)}")


if __name__ == "__main__":
    main()
