"""Offline deterministic gates for evidence.v1. No provider, DB or network."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pydantic import ValidationError

from app.services.evidence_contract import EvidenceClaim, EvidenceRegistry, EvidenceSource, validate_claim


def run_dataset(path: Path) -> dict:
    dataset = json.loads(path.read_text())
    if dataset["dataset_version"] != "evidence_evals.v1" or dataset["contract_version"] != "evidence.v1":
        raise ValueError("unsupported_dataset_version")
    results = []
    for case in dataset["cases"]:
        error = None
        try:
            sources = tuple(EvidenceSource.model_validate(source) for source in case["sources"])
            registry = EvidenceRegistry(case["tenant_id"], sources)
            validate_claim(EvidenceClaim.model_validate(case["candidate"]), registry)
        except ValidationError as exc:
            first = exc.errors()[0]
            error = str(first.get("ctx", {}).get("error", first["type"]))
        except ValueError as exc:
            error = str(exc)
        actual = "reject" if error else "accept"
        passed = actual == case["expected"] and (case.get("error") is None or case["error"] in (error or ""))
        results.append({"id": case["id"], "passed": passed, "actual": actual, "error": error})
    return {
        "dataset_version": dataset["dataset_version"],
        "passed": all(row["passed"] for row in results),
        "case_count": len(results),
        "results": results,
    }


if __name__ == "__main__":
    report = run_dataset(ROOT / "evals/evidence/evidence_v1.json")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
