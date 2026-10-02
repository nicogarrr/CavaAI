"""C3: los evals de las 4 capas LLM son una puerta de CI.

Patron el de ``tests/test_offline_eval_gates.py``: el runner se ejecuta por
subprocess (no se importa) para que el contrato de exit code sea el que se
prueba. Ahi se comprueba ademas que el dataset tiene la forma prometida
(>=40 casos, >=10 por capa, >=6 controles negativos) y que cada puerta no
omitible MUERDE cuando le falta su clave: sin ese test, borrar
``expected.degraded`` de un caso dejaria la puerta en verde.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "evals" / "llm" / "llm_layers_v1.json"


def _dataset() -> dict:
    return json.loads(DATASET_PATH.read_text(encoding="utf-8"))


def test_llm_layer_evals_pass_all_gates():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_llm_evals.py")],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_runner_json_report_is_machine_readable_and_green():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_llm_evals.py"), "--json"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["failures"] == []
    assert report["total_checks"] > 0
    assert min(report["executed"].values()) > 0, "una puerta que nunca corrio"


def test_dataset_covers_the_four_layers_with_enough_cases():
    dataset = _dataset()
    cases = dataset["cases"]
    assert len(cases) >= 40
    per_layer: dict[str, int] = {}
    for case in cases:
        per_layer[case["layer"]] = per_layer.get(case["layer"], 0) + 1
    assert set(per_layer) == {"kpi_extraction", "principles", "narrative", "debate"}
    for layer, count in per_layer.items():
        assert count >= 10, (layer, count)


def test_dataset_spreads_every_assessment_category():
    categories = {case["category"] for case in _dataset()["cases"]}
    assert {
        "happy_path",
        "malformed_output",
        "unknown_label",
        "out_of_range_confidence",
        "provider_failure_shape",
        "fallback_degraded",
        "hallucinated_number",
        "evidence_leak",
        "contradiction",
        "refusal_correcto",
    } <= categories


def test_model_outputs_are_declared_synthetic():
    """Nadie puede creer que estos evals talked to a model."""
    for case in _dataset()["cases"]:
        assert case["output_origin"] == "synthetic_fixture", case["id"]
        assert isinstance(case["frozen_facts"], dict) and case["frozen_facts"]


def test_negative_controls_actually_fail_their_gate():
    """Los controles negativos demuestran que las puertas muerden."""
    from evals.llm.llm_gates import GATES

    negatives = [c for c in _dataset()["cases"] if c.get("expect_gate_failure")]
    assert len(negatives) >= 6
    assert len({c["expect_gate_failure"] for c in negatives}) >= 4
    for case in negatives:
        gate = GATES[case["expect_gate_failure"]]
        assert gate(case)["passed"] is False, case["id"]


def test_every_non_skippable_gate_fails_when_its_key_is_missing():
    """Puerta por puerta: quitar la clave DEBE producir el no omitible."""
    from evals.llm.llm_gates import GATES, NON_SKIPPABLE_GATES

    sample = next(
        case for case in _dataset()["cases"] if case["layer"] == "kpi_extraction"
    )
    stripped = dict(sample)
    stripped["expected"] = {}
    for gate_name in NON_SKIPPABLE_GATES:
        result = GATES[gate_name](stripped)
        assert result["passed"] is False, gate_name
        assert any("no puede omitirse" in detail for detail in result["details"]), (
            gate_name,
            result["details"],
        )


def test_schema_gate_is_not_skippable_either():
    """`output_schema_valid` sin `model_output` es un fallo, no un abstincion."""
    from evals.llm.llm_gates import GATES

    sample = next(
        case for case in _dataset()["cases"] if case["layer"] == "kpi_extraction"
    )
    stripped = {k: v for k, v in sample.items() if k != "model_output"}
    result = GATES["output_schema_valid"](stripped)
    assert result["passed"] is False
    assert any("no puede omitirse" in detail for detail in result["details"])


def test_dataset_gates_fail_when_coverage_disappears():
    from evals.llm.llm_gates import GATES

    dataset = _dataset()
    one_layer = {"cases": [c for c in dataset["cases"] if c["layer"] == "debate"]}
    result = GATES["layers_all_covered"]({"id": "dataset", "dataset": one_layer})
    assert result["passed"] is False
    assert any("kpi_extraction" in detail for detail in result["details"])

    no_negatives = {
        "cases": [c for c in dataset["cases"] if not c.get("expect_gate_failure")]
    }
    result = GATES["negative_controls_present"]({"id": "dataset", "dataset": no_negatives})
    assert result["passed"] is False


def test_gate_fires_on_a_provider_failure_presented_as_a_normal_answer():
    """El fallo mas caro: el proveedor cae y el sistema contesta con confianza."""
    from evals.llm.llm_gates import GATES

    case = next(
        c for c in _dataset()["cases"] if c["id"] == "narr-provider-answer-001"
    )
    result = GATES["provider_failure_is_degraded_not_answered"](case)
    assert result["passed"] is False
    assert any("origen" in detail for detail in result["details"])

# ---------------------------------------------------------------- hermeticidad
#
# El workflow llm-evals instalaba a proposito solo stdlib + lo minimo: si el
# judge importaba app.llm o una libreria de red, el CI se rompia solo. Ahora el
# workflow instala el lock completo (uv sync --frozen) y esa red de seguridad
# ya no existe: este test es quien la sustituye. El runner se ejecuta con un
# bloqueador de imports para el paquete de la app y para las librerias de red /
# LLM / modelos de datos del proyecto; si el judge o las puertas tocan alguna,
# el subprocess falla con ImportError.

_BLOCKED_TOP_LEVEL = (
    "app",
    "pydantic",
    "pydantic_settings",
    "httpx",
    "requests",
    "aiohttp",
    "openai",
    "anthropic",
    "qdrant_client",
    "sqlalchemy",
    "fastapi",
)

_BLOCKER_PREAMBLE = f"""
import importlib.abc, runpy, sys
BLOCKED = {_BLOCKED_TOP_LEVEL!r}

class _Block(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in BLOCKED:
            raise ImportError("hermeticidad: el judge no puede importar " + name)
        return None

sys.meta_path.insert(0, _Block())
"""


def _run_with_blocked_imports(extra: str) -> subprocess.CompletedProcess[str]:
    code = _BLOCKER_PREAMBLE + extra
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(ROOT),
    )


def test_el_bloqueador_de_imports_muerde():
    """Control positivo: sin esto, el test de abajo pasaria aunque no bloqueara nada."""
    for name in ("app", "app.llm", "pydantic", "httpx"):
        result = _run_with_blocked_imports(f"import {name}\n")
        assert result.returncode != 0, name
        assert "hermeticidad" in result.stderr, result.stderr


def test_el_judge_y_las_puertas_corren_sin_app_ni_librerias_de_red():
    script = ROOT / "scripts" / "run_llm_evals.py"
    result = _run_with_blocked_imports(
        f"sys.argv = [{str(script)!r}]\n"
        f"runpy.run_path({str(script)!r}, run_name='__main__')\n"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "hermeticidad" not in result.stderr, result.stderr
