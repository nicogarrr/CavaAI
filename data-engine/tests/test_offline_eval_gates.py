"""Stage 5: los hard gates offline son un gate de CI (corren en Backend quality)."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_offline_eval_dataset_passes_all_gates():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_offline_evals.py")],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_dataset_covers_assessment_categories():
    dataset = json.loads((ROOT / "evals" / "thesis_quality_v1.json").read_text())
    categories = {case["category"] for case in dataset["cases"]}
    assert {
        "sufficient_evidence",
        "insufficient_evidence",
        "contradictory_stale_evidence",
        "debate_bounds",
        "provider_failure_shape",
        "approval_replay_idempotency",
        "negative_control",
    } <= categories
    assert len(dataset["cases"]) >= 20


def test_negative_controls_actually_fail_their_gate():
    """Los controles negativos demuestran que los gates muerden."""
    from evals.gates import GATES

    dataset = json.loads((ROOT / "evals" / "thesis_quality_v1.json").read_text())
    negatives = [c for c in dataset["cases"] if c.get("expect_gate_failure")]
    assert len(negatives) >= 4
    for case in negatives:
        gate = GATES[case["expect_gate_failure"]]
        assert gate(case)["passed"] is False, case["id"]
