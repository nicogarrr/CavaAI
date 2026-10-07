"""Versioned adversarial cases run against the production evidence boundary."""

from pathlib import Path

from scripts.run_evidence_evals import run_dataset


def test_versioned_adversarial_dataset():
    root = Path(__file__).resolve().parents[1]
    report = run_dataset(root / "evals/evidence/evidence_v1.json")
    assert report["case_count"] == 30
    assert report["passed"], report["results"]
