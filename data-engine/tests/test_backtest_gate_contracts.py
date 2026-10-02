"""Contrato de los hard gates del backtest: el runner y los gates no omitibles.

Dos cosas se comprueban aqui, y las dos importan mas de lo que parece:

1. **El runner es un gate de CI.** Si ``run_backtest_evals.py`` dejara de
   correr en verde, el dataset podria haberse adulterado y nadie se enteraria.
2. **Las puertas no omitibles fallan cuando falta su clave.** Un gate que
   devuelve "no aplica" ante una clave ausente es indistinguible de un gate
   roto, y esa indistinguibilidad es exactamente como un backtest se fraudulenta
   solo sin que nadie lo note.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evals.backtest.backtest_gates import (  # noqa: E402
    GATES,
    MISSING_KEY_MESSAGES,
    NON_SKIPPABLE_GATES,
    gate_no_invented_numbers,
    gate_no_lookahead,
    run_case,
)

DATASET = ROOT / "evals" / "backtest" / "backtest_v1.json"
RUNNER = ROOT / "scripts" / "run_backtest_evals.py"


@pytest.fixture(scope="module")
def dataset() -> dict:
    return json.loads(DATASET.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def clean_case(dataset: dict) -> dict:
    for case in dataset["cases"]:
        if case["category"] == "valid_replay":
            return case
    raise AssertionError("el dataset no tiene ningun caso valid_replay")


# ------------------------------------------------------------------ el runner


def test_backtest_eval_runner_passes():
    """El dataset congelado tiene que estar en verde con el codigo actual."""
    result = subprocess.run(
        [sys.executable, str(RUNNER)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Todos los gates en verde" in result.stdout


def test_runner_emits_machine_readable_output_for_ci():
    result = subprocess.run(
        [sys.executable, str(RUNNER), "--json"],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["failures"] == []
    assert payload["checks"] > 0
    assert set(payload["coverage"]) == set(GATES)


def test_runner_fails_when_a_positive_case_breaks(dataset, tmp_path):
    """El runner tiene que ser capaz de fallar, no solo de pasar.

    Se copia el dataset con un caso positivo mutilado y se ejecuta el runner
    contra la copia. Si devolviera 0 igual, la cobertura que da no valdria nada.
    """
    broken = json.loads(json.dumps(dataset))
    target = next(case for case in broken["cases"] if case["category"] == "valid_replay")
    # A FY2999 fact that made it into the snapshot the engine consumed. This is
    # the exact shape of a real leak, not a hand-written "should fail" marker.
    target["artifact"]["used_periods"].append(
        {
            "metric": "revenue",
            "raw": "2999-12-31",
            "end_date": "2999-12-31",
            "precision": "exact_date",
            "source_published_on": "2999-03-01",
        }
    )
    broken_path = tmp_path / "backtest_broken.json"
    broken_path.write_text(json.dumps(broken), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(RUNNER), "--dataset", str(broken_path)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 1
    assert "no_lookahead fallo" in result.stdout
    assert "FALLOS" in result.stdout


def test_runner_reports_a_gate_that_never_ran(tmp_path):
    """Una puerta que no se ejercita esta muerta, y hay que decirlo.

    Se genera un dataset donde un gate no aparece en ningun ``applies_to``.
    """
    trimmed = {
        "version": "trimmed",
        "cases": [
            {
                "id": "solo-schema",
                "category": "valid_replay",
                "expected": {"as_of": "2025-06-30", "evidence_cutoff": "2025-06-30"},
                "frozen_facts": {"revenue": [1000.0]},
                "applies_to": ["net_neutral_honest"],
                "artifact": {
                    "as_of": "2025-06-30",
                    "evidence_cutoff": "2025-06-30",
                    "status": "ok",
                    "fair_value": 10.0,
                    "current_price": 9.0,
                    "bear_value": 8.0,
                    "base_value": 10.0,
                    "bull_value": 12.0,
                    "degraded": False,
                    "degraded_reason": None,
                    "source_coverage_score": 100,
                    "n_claims": 1,
                    "n_claims_with_evidence": 1,
                    "replay_hash": "a" * 64,
                    "replay_hash_again": "a" * 64,
                    "claims": [{"text": "Revenue 1000 grows.", "metric": "revenue"}],
                    "siblings": [],
                },
            }
        ],
    }
    path = tmp_path / "trimmed.json"
    path.write_text(json.dumps(trimmed), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(RUNNER), "--dataset", str(path)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 1
    assert "NUNCA SE EJECUTO" in result.stdout
    assert "nunca se ejecutaron" in result.stdout


# ------------------------------------------------------- forma del dataset


def test_dataset_is_big_enough_and_declares_its_traps(dataset):
    assert len(dataset["cases"]) >= 30
    categories = {case["category"] for case in dataset["cases"]}
    assert {
        "valid_replay",
        "insufficient_data",
        "lookahead_trap_fiscal_year_2999",
        "lookahead_trap_filing_date",
        "lookahead_trap_thesis_publication",
        "lookahead_trap_period_leak",
        "negative_control",
    } <= categories


def test_dataset_has_at_least_eight_negative_controls(dataset):
    negatives = [case for case in dataset["cases"] if case.get("expect_gate_failure")]
    assert len(negatives) >= 8


def test_every_negative_control_actually_fails_its_declared_gate(dataset):
    """Un control negativo que no muerde es decoracion."""
    for case in dataset["cases"]:
        gate_name = case.get("expect_gate_failure")
        if not gate_name:
            continue
        assert gate_name in GATES, case["id"]
        result = GATES[gate_name](case)
        assert result["passed"] is False, f"{case['id']} debia fallar {gate_name}"


def test_every_positive_case_passes_every_gate_it_declares(dataset):
    for case in dataset["cases"]:
        if case.get("expect_gate_failure"):
            continue
        for gate_name, gate in GATES.items():
            declared = case.get("applies_to")
            if declared is not None and gate_name not in declared:
                continue
            result = gate(case)
            assert result["passed"] is True, (
                f"{case['id']}/{gate_name}: {'; '.join(result['details'])}"
            )


def test_every_gate_is_exercised_by_the_dataset(dataset):
    exercised = {
        gate_name
        for case in dataset["cases"]
        for gate_name in GATES
        if case.get("applies_to") is None or gate_name in case["applies_to"]
    }
    assert exercised == set(GATES)


def test_dataset_is_deterministic(dataset):
    """Regenerado, el JSON tiene que ser identico byte a byte.

    Un dataset que cambia entre ejecuciones hace imposible saber si un fallo del
    runner es un fallo real o una regeneracion.
    """
    before = DATASET.read_bytes()
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_backtest_eval_dataset.py")],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert DATASET.read_bytes() == before


# ------------------------------------------- puertas no omitibles, una a una


def test_non_skippable_gates_fail_when_their_key_is_missing(clean_case):
    """Puerta por puerta: quitar la clave que verifica debe hacer FALLAR.

    Este es el contrato que evita que un gate se desactive a si mismo. Si
    ``expected.as_of`` no esta, no hay fecha contra la que auditar, asi que
    ``no_lookahead`` no puede decir "no aplica": no puede hacer nada, y eso no es
    pasar.
    """
    mutations = {
        "no_lookahead": lambda case: case["expected"].pop("as_of", None),
        "evidence_cutoff_respected": lambda case: case["expected"].pop(
            "evidence_cutoff", None
        ),
        "no_invented_numbers": lambda case: case.pop("frozen_facts", None),
        "idempotent_replay": lambda case: case["artifact"].pop("replay_hash", None),
        "source_coverage_score_present": lambda case: case["artifact"].update(
            {"source_coverage_score": None, "n_claims": 2}
        ),
    }
    assert set(mutations) == set(NON_SKIPPABLE_GATES)
    for gate_name, mutate in mutations.items():
        case = json.loads(json.dumps(clean_case))
        mutate(case)
        result = GATES[gate_name](case)
        assert result["passed"] is False, f"{gate_name} paso sin su clave"
        assert any(
            "no puede omitirse" in detail for detail in result["details"]
        ), f"{gate_name}: {result['details']}"


def test_each_non_skippable_gate_declares_its_missing_key_message():
    for gate_name in NON_SKIPPABLE_GATES:
        assert gate_name in MISSING_KEY_MESSAGES
        assert "no puede omitirse" in MISSING_KEY_MESSAGES[gate_name]


def test_no_lookahead_rejects_a_case_with_no_expected_as_of():
    result = gate_no_lookahead({"artifact": {}, "expected": {}})
    assert result["passed"] is False
    assert result["details"] == ["falta expected.as_of: el gate no puede omitirse"]


def test_no_lookahead_rejects_an_artifact_whose_as_of_disagrees():
    result = gate_no_lookahead(
        {"artifact": {"as_of": "2024-01-01"}, "expected": {"as_of": "2025-01-01"}}
    )
    assert result["passed"] is False


def test_no_lookahead_rejects_a_cell_that_audits_nothing():
    """Una celda sin periodos auditados pasaria el gate sin comprobar nada.

    Cuatro de los ocho motores leen ``FinancialFact`` directamente y no pasan por
    el snapshot, asi que sus periodos solo aparecen en el trace del motor. Por eso
    el gate exige que se audite algo.
    """
    result = gate_no_lookahead(
        {
            "artifact": {"as_of": "2025-06-30", "status": "ok", "fair_value": 10.0},
            "expected": {"as_of": "2025-06-30"},
        }
    )
    assert result["passed"] is False
    assert any("sin comprobar nada" in detail for detail in result["details"])


def test_no_lookahead_rejects_an_inflated_violation_list():
    """Declarar como violacion algo que no es posterior al corte infla el recuento.

    Un informe con mas rechazos de los reales hace que un backtest sano parezca
    roto, que es la forma de que la alerta se vuelva ruido y nadie la mire.
    """
    result = gate_no_lookahead(
        {
            "artifact": {
                "as_of": "2025-06-30",
                "status": "ok",
                "used_periods": [{"metric": "revenue", "end_date": "2024-12-31"}],
                "lookahead_violations_detail": [{"metric": "revenue", "end_date": "2020-01-01"}],
            },
            "expected": {"as_of": "2025-06-30"},
        }
    )
    assert result["passed"] is False
    assert any("infla el recuento" in detail for detail in result["details"])


def test_no_lookahead_rejects_a_leak_that_still_publishes_a_value():
    result = gate_no_lookahead(
        {
            "artifact": {
                "as_of": "2025-06-30",
                "status": "ok",
                "fair_value": 10.0,
                "lookahead_violations": ["revenue (fact 9): futuro"],
                "used_periods": [{"metric": "revenue", "end_date": "2024-12-31"}],
            },
            "expected": {"as_of": "2025-06-30"},
        }
    )
    assert result["passed"] is False
    assert any("status=ok" in detail for detail in result["details"])


def test_no_lookahead_audits_the_engine_trace_not_only_the_snapshot():
    """El trace del motor se audita con la misma regla que el snapshot."""
    leaking_trace = {
        "artifact": {
            "as_of": "2025-06-30",
            "status": "rejected_lookahead",
            "used_periods": [],
            "engine_trace_periods": [{"metric": "book_value", "end_date": "2999-12-31"}],
        },
        "expected": {"as_of": "2025-06-30"},
    }
    assert gate_no_lookahead(leaking_trace)["passed"] is False
    leaking_trace["artifact"]["engine_trace_periods"][0]["end_date"] = "2024-12-31"
    assert gate_no_lookahead(leaking_trace)["passed"] is True


def test_no_invented_numbers_honours_the_spanish_decimal_comma():
    """``1,2`` es uno coma dos, no doce.

    Si se normalizara mal, "1,2" pasaria por un hecho de 12 y una magnitud
    inventada se colaria por la puerta de atras de la normalizacion.
    """
    case = {
        "frozen_facts": {"revenue": [1.2]},
        "artifact": {"claims": [{"text": "Revenue 1,2 grows.", "metric": "revenue"}]},
    }
    assert gate_no_invented_numbers(case)["passed"] is True
    case["artifact"]["claims"][0]["text"] = "Revenue 98765 grows."
    assert gate_no_invented_numbers(case)["passed"] is False


def test_no_invented_numbers_only_accepts_the_declared_metric():
    case = {
        "frozen_facts": {"revenue": [1000.0], "net_debt": [300.0]},
        "artifact": {"claims": [{"text": "Net debt 1000 falls.", "metric": "net_debt"}]},
    }
    assert gate_no_invented_numbers(case)["passed"] is False


def test_run_case_executes_every_gate(clean_case):
    results = run_case(clean_case)
    assert {item["gate"] for item in results} == set(GATES)
    assert all(item["passed"] for item in results)


def test_gate_results_have_the_declared_shape(clean_case):
    for item in run_case(clean_case):
        assert set(item) == {"gate", "passed", "details"}
        assert isinstance(item["passed"], bool)
        assert isinstance(item["details"], list)
        assert all(isinstance(detail, str) for detail in item["details"])
