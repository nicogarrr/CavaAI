"""C3: contratos del judge determinista de las 4 capas LLM.

Lo que se prueba aqui es que el juez de los evals es de fiar:

- Es DETERMINISTA: dos invocaciones producen el mismo informe byte a byte.
- NO es un LLM: en caliente no importa ni invoca nada de ``app/llm/`` ni de
  ``app/services/jev_gates.py``, y no abre red (loopback permitido). Se
  comprueba en un subprocess con un guard de imports que lanza
  AssertionError y ``socket.socket.connect`` bloqueado.
- Sus espejos de contrato NO SE PUDREN: las claves obligatorias y los
  vocabularios se contrastan contra los ``ResponseFormat.json_schema`` reales
  y contra ``jev_gates.DEBATE_VERDICT_CRITERIA``.
- ``_norm_number`` no fabrica cifras, y una etiqueta desconocida o una
  confianza no finita / fuera de [0,1] se rechazan igual que en
  ``jev_choice_or_none``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "evals" / "llm" / "llm_layers_v1.json"

HERMETIC_SCRIPT = """
import json, socket, sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))

BANNED = ("app.llm", "app.services.jev_gates", "openai", "httpx", "requests")


class _BlockImports:
    def find_spec(self, fullname, path=None, target=None):
        for prefix in BANNED:
            if fullname == prefix or fullname.startswith(prefix + "."):
                raise AssertionError("el judge no puede importar " + fullname)
        return None


sys.meta_path.insert(0, _BlockImports())

LOOPBACK = {"127.0.0.1", "::1", "localhost"}
_original_connect = socket.socket.connect


def _blocked(self, address, *args, **kwargs):
    host = address[0] if isinstance(address, tuple) else str(address)
    if str(host) in LOOPBACK:
        return _original_connect(self, address, *args, **kwargs)
    raise AssertionError("el judge no puede abrir red hacia " + str(host))


socket.socket.connect = _blocked

from evals.llm.deterministic_judge import judge_case, no_network

with no_network():
    dataset = json.loads((ROOT / "evals" / "llm" / "llm_layers_v1.json").read_text(encoding="utf-8"))
    report = [judge_case(case).to_dict() for case in dataset["cases"]]

print(json.dumps(report, ensure_ascii=False, sort_keys=True))
"""


def _cases() -> list[dict]:
    return json.loads(DATASET_PATH.read_text(encoding="utf-8"))["cases"]


def _hermetic_run() -> str:
    result = subprocess.run(
        [sys.executable, "-c", HERMETIC_SCRIPT, str(ROOT)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_judge_never_imports_a_provider_or_jev():
    """Sin app.llm, sin jev_gates, sin cliente HTTP y sin red."""
    _hermetic_run()


def test_judge_is_byte_identical_across_runs():
    first = _hermetic_run()
    second = _hermetic_run()
    assert first == second
    assert first.strip()


def test_judge_case_is_deterministic_in_process():
    from evals.llm.deterministic_judge import judge_case

    for case in _cases()[:6]:
        one = json.dumps(judge_case(case).to_dict(), ensure_ascii=False, sort_keys=True)
        other = json.dumps(judge_case(case).to_dict(), ensure_ascii=False, sort_keys=True)
        assert one == other, case["id"]


def test_norm_number_does_not_fabricate_numbers():
    from evals.gates import _norm_number

    assert _norm_number("1,2") == 1.2
    assert _norm_number("1,234") == 1234.0
    assert _norm_number("1.234,5") == 1234.5
    # Lo que no se puede leer, no se inventa: tres separadores no son un numero.
    assert _norm_number("1.234.567") is None
    # Lo que no se puede leer, no se inventa.
    assert _norm_number("") is None
    assert _norm_number("   ") is None
    assert _norm_number("sin cifras") is None
    assert _norm_number("1.2.3") is None
    assert _norm_number("N/A") is None


def test_spanish_decimal_comma_is_shared_by_both_sides_of_the_gate():
    """Si el fixture y el frozen fact usan la misma regla, la grounding cierra."""
    from evals.llm.llm_gates import GATES

    grounded = next(c for c in _cases() if c["id"] == "kpi-decimal-comma-001")
    assert GATES["no_hallucinated_numbers"](grounded)["passed"] is True
    # "1,25" NO es 12,5: la coma decimal no se reescribe como separador de miles.
    mangled = next(c for c in _cases() if c["id"] == "kpi-hallucinated-002-coma")
    assert GATES["no_hallucinated_numbers"](mangled)["passed"] is False


def test_unknown_label_is_rejected_like_jev_does():
    from evals.llm.deterministic_judge import production_verdict, strict_verdict
    from evals.llm.llm_gates import GATES

    # `re.search` de produccion casa dentro de la palabra; un token, no.
    assert production_verdict("The bullishness of the moat is doubtful") == "bullish"
    assert strict_verdict("The bullishness of the moat is doubtful") is None
    assert production_verdict("VEREDICTO: neutral |algo mas") == "neutral"
    assert strict_verdict("VEREDICTO: neutral |algo mas") == "neutral"

    case = next(c for c in _cases() if c["id"] == "debate-unknown-label-001")
    result = GATES["no_unknown_labels"](case)
    assert result["passed"] is False
    assert any("token independiente" in detail for detail in result["details"])


def test_unknown_metric_label_is_rejected():
    from evals.llm.llm_gates import GATES

    case = next(c for c in _cases() if c["id"] == "kpi-unknown-label-001")
    result = GATES["no_unknown_labels"](case)
    assert result["passed"] is False
    assert any("revenue_margins" in detail for detail in result["details"])


@pytest.mark.parametrize("value", [-0.1, 1.01, 2.0, float("nan"), float("inf")])
def test_confidence_out_of_range_or_non_finite_is_rejected(value):
    from evals.llm.deterministic_judge import check_confidences

    case = {
        "id": "sintetico",
        "layer": "kpi_extraction",
        "frozen_facts": {"revenue": 1.0},
        "model_output": {
            "observations": [
                {
                    "metric_key": "revenue",
                    "raw_label": "Ingresos",
                    "raw_value": "1",
                    "raw_unit": "EUR millions",
                    "period": "FY2025",
                    "fiscal_year": 2025,
                    "fiscal_quarter": "FY",
                    "chunk_id": 1,
                    "quote": "ingresos de 1",
                    "confidence": value,
                }
            ]
        },
        "layer_output": {"degraded": False, "abstained": False},
        "expected": {"degraded": False, "abstain": False},
    }
    assert check_confidences(case), value


@pytest.mark.parametrize("value", [0.0, 0.5, 1.0])
def test_confidence_inside_range_passes(value):
    from evals.llm.deterministic_judge import check_confidences

    assert check_confidences(
        {
            "layer": "kpi_extraction",
            "model_output": {"observations": [{"confidence": value}]},
            "layer_output": {},
        }
    ) == []


def test_boolean_confidence_is_not_a_number():
    """`True` es un int en Python: aceptarlo como 1.0 seria calibrar nada."""
    from evals.llm.deterministic_judge import check_confidences

    problems = check_confidences(
        {
            "layer": "kpi_extraction",
            "model_output": {"observations": [{"confidence": True}]},
            "layer_output": {},
        }
    )
    assert problems


def test_mirrored_kpi_contract_matches_the_real_schema():
    from app.services.kpi_extraction_service import KPIExtractionService
    from evals.llm.deterministic_judge import (
        FISCAL_QUARTERS,
        KPI_OBSERVATION_KEYS,
    )

    real = KPIExtractionService._schema(["revenue"])
    item = real["properties"]["observations"]["items"]
    assert tuple(item["required"]) == KPI_OBSERVATION_KEYS
    assert tuple(item["properties"]["fiscal_quarter"]["enum"]) == (
        "Q1", "Q2", "Q3", "Q4", "FY",
    )
    assert set(item["properties"]["fiscal_quarter"]["enum"]) == set(FISCAL_QUARTERS)
    assert item["properties"]["confidence"]["minimum"] == 0
    assert item["properties"]["confidence"]["maximum"] == 1
    assert item["additionalProperties"] is False


def test_mirrored_principle_contract_matches_the_real_schema():
    from app.services.knowledge_library_service import KnowledgeLibraryService
    from evals.llm.deterministic_judge import PRINCIPLE_KEYS

    real = KnowledgeLibraryService._principle_schema()
    item = real["properties"]["principles"]["items"]
    assert tuple(item["required"]) == PRINCIPLE_KEYS
    assert item["additionalProperties"] is False


def test_mirrored_narrative_contract_matches_the_real_schema():
    from app.services.thesis_narrative_llm import _SECTIONS_OUTPUT_SCHEMA
    from evals.llm.deterministic_judge import NARRATIVE_KEYS

    assert tuple(_SECTIONS_OUTPUT_SCHEMA["required"]) == NARRATIVE_KEYS
    assert _SECTIONS_OUTPUT_SCHEMA["properties"]["section_ids"]["minItems"] == 1
    assert _SECTIONS_OUTPUT_SCHEMA["properties"]["section_ids"]["maxItems"] == 8


def test_mirrored_verdict_labels_match_jev_gates():
    from app.services.jev_gates import DEBATE_VERDICT_CRITERIA
    from evals.llm.deterministic_judge import DEBATE_VERDICT_LABELS

    assert set(DEBATE_VERDICT_LABELS) == set(DEBATE_VERDICT_CRITERIA)


def test_no_network_guard_blocks_everything_but_loopback():
    import socket

    from evals.llm.deterministic_judge import no_network

    original = socket.socket.connect
    with no_network():
        assert socket.socket.connect is not original
        with pytest.raises(AssertionError):
            socket.socket().connect(("93.184.216.34", 80))
    assert socket.socket.connect is original