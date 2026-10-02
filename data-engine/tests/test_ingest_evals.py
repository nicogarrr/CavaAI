"""C4: los hard gates de precision de ingesta son una puerta de CI.

Igual que `test_offline_eval_gates.py` para las tesis: el runner se ejecuta por
subprocess (es un script, no una funcion) y su salida es la que se juzga. El
dataset congelado debe pasar todas sus puertas, con las cuatro metricas por
encima de su umbral, con las tres familias de fuente y con los controles
negativos mordiendo de verdad.

El runner tarda ~20 s (78 casos contra la ingesta real, cada uno con su propia
base SQLite en memoria), asi que las corridas se cachean por sesion: llamarlo
cinco veces para leer cinco campos seria tests lentos, no tests endured.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_ingest_evals.py"
DATASET = ROOT / "evals" / "ingest" / "ingest_v1.json"
FIXTURES = ROOT / "tests" / "fixtures" / "ingest_eval"

THRESHOLDS = {
    "field_accuracy": 0.98,
    "period_attribution_accuracy": 0.95,
    "source_attribution_accuracy": 0.99,
    "abstention_rate": 1.0,
}


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(RUNNER), *args],
        capture_output=True,
        text=True,
        timeout=900,
        cwd=str(ROOT),
    )


@pytest.fixture(scope="session")
def text_report() -> str:
    result = _run()
    assert result.returncode == 0, result.stdout[-6000:] + result.stderr[-4000:]
    return result.stdout


@pytest.fixture(scope="session")
def json_report() -> dict:
    result = _run("--json")
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-4000:]
    return json.loads(result.stdout)


@pytest.fixture(scope="session")
def dataset() -> dict:
    return json.loads(DATASET.read_text(encoding="utf-8"))


def test_runner_passes_every_gate(text_report):
    assert "Todos los gates en verde." in text_report
    assert "NUNCA SE EJECUTO" not in text_report
    assert "SIN CASOS" not in text_report


def test_four_metrics_are_above_their_threshold(json_report):
    metrics = json_report["metrics"]
    assert set(metrics) == set(THRESHOLDS)
    for name, threshold in THRESHOLDS.items():
        data = metrics[name]
        assert data["total"] > 0, f"{name} no midio nada: un umbral sobre cero no es un control"
        assert data["value"] >= threshold, f"{name}={data['value']} < {threshold}"


def test_dataset_covers_the_three_source_families(json_report, dataset):
    families = {case["family"] for case in dataset["cases"]}
    assert {"sec", "fmp", "esef"} <= families
    for family, count in json_report["family_cases"].items():
        assert count > 0, f"la familia {family} no ejecuto ningun caso"
    summary = dataset["summary"]
    assert summary["cases"] >= 60
    assert summary["families"]["sec"] >= 25
    assert summary["families"]["fmp"] >= 12
    assert summary["families"]["esef"] >= 12
    assert summary["negative_controls"] >= 8
    assert summary["degradation_cases"] >= 5


def test_every_gate_actually_runs(json_report):
    from evals.ingest.ingest_gates import GATES, NON_SKIPPABLE_GATES

    coverage = json_report["gate_coverage"]
    assert set(coverage) == set(GATES)
    for name, count in coverage.items():
        assert count > 0, f"la puerta {name} nunca se ejecuto: no es una puerta, es decoracion"
    for name in NON_SKIPPABLE_GATES:
        assert coverage[name] == json_report["cases"], (
            f"{name} es no omitible y debe correr en todos los casos, no en {coverage[name]}"
        )


def test_negative_controls_actually_bite(dataset):
    from evals.ingest.ingest_gates import GATES, applies_to

    negatives = [case for case in dataset["cases"] if case.get("expect_gate_failure")]
    assert len(negatives) >= 8
    covered = set()
    for case in negatives:
        gate_name = case["expect_gate_failure"]
        covered.add(gate_name)
        assert gate_name in GATES, f"{case['id']} declara una puerta inexistente"
        assert gate_name in case["applies_to"]
        assert applies_to(case, gate_name)
    assert {
        "no_lookahead",
        "official_only_if_index_verified",
        "absent_fields_reported_as_null",
    } <= covered


def test_degradation_cases_are_honest_and_silent(dataset):
    degradations = [case for case in dataset["cases"] if case["category"] == "degradation"]
    assert len(degradations) >= 5
    for case in degradations:
        assert case["expected"].get("absent_metrics"), f"{case['id']} no declara que se ausenta"
        if not case["expected"].get("facts"):
            assert case["expected"].get("extracts_nothing"), (
                f"{case['id']} es una degradacion total: no puede publicar hechos"
            )
        else:
            # Degradacion parcial: lo que responde se ingiere, lo demas se declara ausente.
            assert case["expected"]["absent_metrics"], (
                f"{case['id']} ingiere algo y no declara la cobertura que le falta"
            )
    assert {case["family"] for case in degradations} == {"sec", "fmp", "esef"}


def test_runner_is_deterministic():
    assert _run("--json").stdout == _run("--json").stdout, (
        "dos corridas del runner difieren: el eval no es reproducible"
    )


def test_runner_fails_when_a_threshold_is_unreachable():
    """Con un umbral imposible el runner tiene que salir con 1, no bajar el liston."""
    import scripts.run_ingest_evals as runner
    from evals.ingest.ingest_gates import GATES  # noqa: F401 - ancla el import del paquete

    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    original = runner.METRICS
    try:
        runner.METRICS = {**THRESHOLDS, "abstention_rate": 1.01}
        report = runner.run(dataset)
    finally:
        runner.METRICS = original
    assert report["passed"] is False
    assert any("abstention_rate" in failure for failure in report["failures"])


def test_corpus_is_declared_synthetic(dataset):
    readme = (FIXTURES / "README.md").read_text(encoding="utf-8")
    assert "synthetic_fixture" in readme
    assert dataset["note"]
    assert "sintetico" in dataset["note"].lower()
