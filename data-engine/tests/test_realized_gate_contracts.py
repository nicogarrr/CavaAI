"""D3: contrato de los hard gates del retorno realizado.

Un gate que se puede silenciar no es un gate. Estos tests comprueban tres
cosas: que la forma del resultado sea la del repo, que los gates NO OMITIBLES
fallen fuerte cuando su entrada falta, y que el runner de subprocess salga en
verde con el dataset real y en rojo con uno manipulado.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from evals.gates import _norm_number
from evals.realized.realized_gates import (
    GATES,
    NON_SKIPPABLE_GATES,
    gate_currency_declared_or_null,
    gate_drawdown_sign_consistent,
    gate_horizons_monotonic_in_time,
    gate_idempotent_recompute,
    gate_missing_price_is_not_zero,
    gate_no_invented_numbers,
    gate_no_lookahead_entry,
    gate_outcome_deterministico,
    gate_outcome_reason_present,
    gate_too_early_not_counted_as_wrong,
)

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evals" / "realized" / "realized_v1.json"
RUNNER = ROOT / "scripts" / "run_realized_evals.py"


def _dataset() -> dict:
    return json.loads(DATASET.read_text(encoding="utf-8"))


def _case(case_id: str) -> dict:
    return next(case for case in _dataset()["cases"] if case["id"] == case_id)


def test_every_gate_returns_the_repo_result_shape() -> None:
    case = _case("realized-right-001")
    for name, gate in GATES.items():
        result = gate(case)
        assert set(result) == {"gate", "passed", "details"}, name
        assert result["gate"] == name
        assert isinstance(result["passed"], bool), name
        assert isinstance(result["details"], list), name
        assert all(isinstance(detail, str) for detail in result["details"]), name


def test_the_dataset_is_big_enough_and_has_negative_controls() -> None:
    cases = _dataset()["cases"]
    negatives = [case for case in cases if case.get("expect_gate_failure")]
    assert len(cases) >= 30
    assert len(negatives) >= 8
    assert {case["expect_gate_failure"] for case in negatives} >= {
        "no_lookahead_entry",
        "missing_price_is_not_zero",
        "benchmark_required_for_alpha",
        "currency_declared_or_null",
        "outcome_deterministico",
        "outcome_reason_present",
        "drawdown_sign_consistent",
        "horizons_monotonic_in_time",
        "no_invented_numbers",
        "idempotent_recompute",
        "too_early_not_counted_as_wrong",
    }


def test_every_gate_runs_on_at_least_one_case() -> None:
    dataset = _dataset()
    executed = set()
    for case in dataset["cases"]:
        declared = case.get("applies_to")
        for name in GATES:
            if name in NON_SKIPPABLE_GATES or declared is None or name in declared:
                executed.add(name)
    assert executed == set(GATES)


def test_non_skippable_gates_are_the_three_core_ones() -> None:
    assert set(NON_SKIPPABLE_GATES) == {
        "outcome_deterministico",
        "no_lookahead_entry",
        "missing_price_is_not_zero",
    }
    for name in NON_SKIPPABLE_GATES:
        assert name in GATES


def test_outcome_gate_fails_loudly_without_the_expected_outcome() -> None:
    result = gate_outcome_deterministico({"artifact": {"outcome": "thesis_right"}, "expected": {}})
    assert result["passed"] is False
    assert any("el gate no puede omitirse" in detail for detail in result["details"])


def test_outcome_gate_rejects_an_unknown_class() -> None:
    case = _case("realized-right-001")
    case["artifact"]["outcome"] = "casi_acertada"
    result = gate_outcome_deterministico(case)
    assert result["passed"] is False
    assert "no es una de las" in " ".join(result["details"])


def test_no_lookahead_gate_fails_loudly_without_the_publication_anchor() -> None:
    result = gate_no_lookahead_entry({"artifact": {"horizons": []}, "expected": {}})
    assert result["passed"] is False
    assert any("el gate no puede omitirse" in detail for detail in result["details"])


def test_no_lookahead_gate_rejects_an_entry_before_the_thesis() -> None:
    result = gate_no_lookahead_entry(_case("negative-lookahead-entry-101"))
    assert result["passed"] is False
    assert any("look-ahead" in detail for detail in result["details"])


def test_missing_price_gate_fails_loudly_without_horizons() -> None:
    result = gate_missing_price_is_not_zero({"artifact": {"horizons": []}})
    assert result["passed"] is False
    assert any("el gate no puede omitirse" in detail for detail in result["details"])


def test_missing_price_gate_rejects_a_zero_for_an_unmeasured_horizon() -> None:
    result = gate_missing_price_is_not_zero(_case("negative-missing-price-zero-102"))
    assert result["passed"] is False
    assert any("0" in detail for detail in result["details"])


def test_too_early_never_counts_as_wrong() -> None:
    assert gate_too_early_not_counted_as_wrong(_case("realized-too-early-006"))["passed"]
    assert (
        gate_too_early_not_counted_as_wrong(_case("negative-too-early-as-wrong-103"))[
            "passed"
        ]
        is False
    )


def test_a_falling_price_can_still_be_a_wrong_thesis() -> None:
    """`thesis_wrong` con retorno negativo: es el caso sano, no un fallo."""
    assert gate_too_early_not_counted_as_wrong(_case("realized-wrong-002"))["passed"]


def test_benchmark_gate_rejects_zero_alpha_without_an_index() -> None:
    assert gate_outcome_reason_present(_case("realized-right-001"))["passed"]
    case = _case("negative-alpha-zero-no-benchmark-104")
    from evals.realized.realized_gates import gate_benchmark_required_for_alpha

    assert gate_benchmark_required_for_alpha(case)["passed"] is False


def test_benchmark_gate_requires_a_reason_for_a_missing_alpha() -> None:
    from evals.realized.realized_gates import gate_benchmark_required_for_alpha

    case = _case("realized-no-benchmark-009")
    assert gate_benchmark_required_for_alpha(case)["passed"]
    for horizon in case["artifact"]["horizons"]:
        horizon["alpha_reason"] = None
    assert gate_benchmark_required_for_alpha(case)["passed"] is False


def test_currency_gate_accepts_null_but_not_invented_codes() -> None:
    assert gate_currency_declared_or_null(_case("realized-no-currency-010"))["passed"]
    assert (
        gate_currency_declared_or_null(_case("negative-invented-currency-105"))["passed"]
        is False
    )
    assert (
        gate_currency_declared_or_null(_case("negative-base-return-no-currency-112"))[
            "passed"
        ]
        is False
    )


def test_drawdown_gate_rejects_a_return_the_path_never_visited() -> None:
    assert gate_drawdown_sign_consistent(_case("realized-deep-drawdown-018"))["passed"]
    assert (
        gate_drawdown_sign_consistent(_case("negative-drawdown-vs-return-106"))["passed"]
        is False
    )


def test_horizons_gate_rejects_an_exit_before_the_shorter_horizon() -> None:
    assert gate_horizons_monotonic_in_time(_case("realized-right-001"))["passed"]
    assert (
        gate_horizons_monotonic_in_time(_case("negative-nonmonotonic-107"))["passed"]
        is False
    )


def test_idempotence_gate_tracks_price_corrections() -> None:
    assert gate_idempotent_recompute(_case("realized-right-001"))["passed"]
    assert gate_idempotent_recompute(_case("realized-revised-prices-016"))["passed"]
    assert gate_idempotent_recompute(_case("negative-idempotent-111"))["passed"] is False


def test_idempotence_gate_fails_loudly_without_a_fingerprint() -> None:
    result = gate_idempotent_recompute({"artifact": {"horizons": []}, "expected": {}})
    assert result["passed"] is False
    assert any("el gate no puede omitirse" in detail for detail in result["details"])


def test_no_invented_numbers_reads_the_spanish_decimal_comma() -> None:
    """`14,4 %` es catorce con cuatro, no ciento cuarenta y cuatro."""
    assert _norm_number("14,4") == 14.4
    assert _norm_number("1.234,56") == 1234.56
    assert _norm_number("1,234.56") == 1234.56
    case = _case("realized-right-001")
    assert gate_no_invented_numbers(case)["passed"]
    # Mismo numero escrito con coma: sigue encuentras su hecho congelado.
    case["artifact"]["verdict_reason"] = case["artifact"]["verdict_reason"].replace(
        "14,4", "14,4"
    )
    assert gate_no_invented_numbers(case)["passed"]
    assert gate_no_invented_numbers(_case("negative-invented-number-110"))["passed"] is False


def test_no_invented_numbers_fails_loudly_without_frozen_facts() -> None:
    result = gate_no_invented_numbers({"artifact": {"verdict_reason": "1"}, "frozen_facts": {}})
    assert result["passed"] is False
    assert any("frozen_facts" in detail for detail in result["details"])


def test_runner_green_on_the_real_dataset() -> None:
    result = subprocess.run(
        [sys.executable, str(RUNNER)],  # noqa: S603
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Todos los gates en verde." in result.stdout
    assert "NUNCA SE EJECUTO" not in result.stdout


def test_runner_json_flag_reports_coverage_and_no_failures() -> None:
    result = subprocess.run(
        [sys.executable, str(RUNNER), "--json"],  # noqa: S603
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["passed"] is True
    assert report["failures"] == []
    assert report["never_ran"] == []
    assert set(report["executed"]) == set(GATES)
    assert all(count > 0 for count in report["executed"].values())
    negatives = [row for row in report["rows"] if row["negative_control"]]
    assert len(negatives) >= 8
    assert all(row["status"] == "ok" for row in negatives)


def test_evaluate_reports_a_gate_that_never_runs() -> None:
    """Un dataset que solo ejercita una puerta debe fallar, no salir en verde."""
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import run_realized_evals as runner
    finally:
        sys.path.pop(0)

    stub = {
        "dataset": "stub",
        "cases": [
            {
                "id": "solo-una",
                "applies_to": ["outcome_deterministico"],
                "expected": {"outcome": "thesis_right"},
                "artifact": {
                    "outcome": "thesis_right",
                    "counts_toward_hit_rate": True,
                    "thesis_published_at": "2024-01-02T09:00:00+00:00",
                    "entry_date": "2024-01-02",
                    "entry_price_status": "exact",
                    "horizons": [
                        {
                            "horizon": "6M",
                            "horizon_days": 180,
                            "status": "ok",
                            "exit_date": "2024-07-01",
                            "realized_return": "0.100000",
                            "alpha": "0.050000",
                            "max_drawdown": "-0.010000",
                            "max_run_up": "0.100000",
                        }
                    ],
                },
            }
        ],
    }
    report = runner.evaluate(stub)
    assert report["passed"] is False
    assert "no_invented_numbers" in " ".join(report["never_ran"])


def test_evaluate_rejects_a_negative_control_that_passes() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import run_realized_evals as runner
    finally:
        sys.path.pop(0)

    case = _case("realized-right-001")
    case["expect_gate_failure"] = "no_lookahead_entry"
    report = runner.evaluate({"dataset": "stub", "cases": [case]})
    assert report["passed"] is False
    assert any("debia FALLAR" in failure for failure in report["failures"])


@pytest.mark.parametrize("gate", sorted(GATES))
def test_no_gate_raises_on_any_dataset_case(gate: str) -> None:
    for case in _dataset()["cases"]:
        result = GATES[gate](case)
        assert result["passed"] is True or result["details"], f"{gate} / {case['id']}"
