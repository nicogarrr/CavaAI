"""C3: judge determinista para los evals de las 4 capas LLM.

Sustituye al LLM en TODOS los evals de ``evals/llm/``: nada de red, nada de
embeddings, nada de proveedor. Tres objetivos medibles:

1. ``schema`` - la salida del LLM contra el contrato de la capa: JSON valido,
   campos obligatorios, tipos y enumeraciones, y ``additionalProperties: false``
   como lo pide ``strict=True``. El RANGO de las confiancias no se comprueba
   aqui a proposito: lo posee la puerta ``confidence_in_range``, y que una sola
   puerta sea la que muerde es lo que deja que un control negativo falle
   exactamente una. Los contratos son un ESPEJO local de los
   ``ResponseFormat.json_schema(..., strict=True)`` de ``app/services/*``;
   ``tests/test_llm_judge_contracts.py`` los contrasta contra el codigo real
   para que el espejo no se Pudra.
2. ``grounding`` - toda cifra citada en la salida debe existir en los
   ``frozen_facts`` del caso, normalizada con ``evals.gates._norm_number``
   (coma decimal espanola incluida: ``"1,2"`` -> 1.2, ``"1,234"`` -> 1234.0).
3. ``structure`` - probabilidades que suman 1, ``bear <= bull <= base``,
   veredicto del debate en el conjunto permitido, claim material con evidencia,
   fragmento verbatim dentro de la entrada y honestidad de estado
   (``answer_source`` + ``degraded``).

Dos decisiones deliberadas:

- No importa NADA de ``app/llm/`` ni de ``app/services/jev_gates.py``. El
  judge tiene que correr en un CI sin credenciales y sin dependencias de
  proveedor; los labels espejados (p.ej. los de ``DEBATE_VERDICT_CRITERIA``)
  se contrastan en los tests, no en caliente.
- Replica la semantica de fallo de ``jev_choice_or_none`` (``jev_gates.py``
  L154: "Nunca aceptar etiquetas desconocidas o confidencias fuera de rango").
  Aqui eso no es una excepcion: es un hallazgo. Una etiqueta desconocida o
  una confianza no finita / fuera de ``[0,1]`` NO son una respuesta.
"""

from __future__ import annotations

import json
import math
import re
import socket
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from evals.gates import _norm_number

LAYERS: tuple[str, ...] = ("kpi_extraction", "principles", "narrative", "debate")

# ---------------------------------------------------------------------------
# Espejo de los contratos de salida (`strict=True` => additionalProperties: 0)
# ---------------------------------------------------------------------------

KPI_OBSERVATION_KEYS: tuple[str, ...] = (
    "metric_key",
    "raw_label",
    "raw_value",
    "raw_unit",
    "period",
    "fiscal_year",
    "fiscal_quarter",
    "chunk_id",
    "quote",
    "confidence",
)
PRINCIPLE_KEYS: tuple[str, ...] = (
    "principle",
    "category",
    "application_conditions",
    "exceptions",
    "company_tickers",
    "exact_fragment",
    "chunk_id",
    "confidence",
)
NARRATIVE_KEYS: tuple[str, ...] = ("section_ids",)
DEBATE_KEYS: tuple[str, ...] = ("bull_case", "bear_case", "judge_text")

LAYER_ROOT_KEY: dict[str, str] = {
    "kpi_extraction": "observations",
    "principles": "principles",
    "narrative": "section_ids",
    # El debate no es una coleccion: sus tres textos cuelgan de la raiz.
    "debate": "sides",
}
LAYER_ITEM_KEYS: dict[str, tuple[str, ...]] = {
    "kpi_extraction": KPI_OBSERVATION_KEYS,
    "principles": PRINCIPLE_KEYS,
    "narrative": NARRATIVE_KEYS,
    "debate": DEBATE_KEYS,
}

# ---------------------------------------------------------------------------
# Vocabularios cerrados. Deliberadamente MAS estrictos que produccion: el
# schema real deja `category` libre porque el registry por empresa no puede
# congelarse en un dataset. Un vocabulario cerrado es lo que permite que un
# gate determinista detecte la deriva en vez de aceptarla.
# ---------------------------------------------------------------------------

FISCAL_QUARTERS = frozenset({"Q1", "Q2", "Q3", "Q4", "FY"})
# Espejo de app.services.jev_gates.DEBATE_VERDICT_CRITERIA (claves).
DEBATE_VERDICT_LABELS: tuple[str, ...] = ("bearish", "neutral", "bullish")
PRINCIPLE_CATEGORIES = frozenset({
    "moat",
    "pricing_power",
    "capital_allocation",
    "balance_sheet",
    "management",
    "growth",
    "cyclicality",
    "regulation",
    "accounting_quality",
})
ANSWER_SOURCES: tuple[str, ...] = (
    "llm_judge",
    "jev_judge",
    "regex_fallback",
    "deterministic_fallback",
    "abstained",
)
# Las tres unicas fuentes que pueden declarar "no lo se".
DEGRADED_ANSWER_SOURCES = frozenset({"regex_fallback", "deterministic_fallback", "abstained"})
MODEL_ANSWER_SOURCES = frozenset({"llm_judge", "jev_judge"})
# Lo que escribe `_deterministic_verdict` en thesis_debate_service.
DEGRADED_DISCLOSURE_MARKERS: tuple[str, ...] = ("no disponible", "determinista", "degradad")
PROVIDER_FAILURE_SHAPES = frozenset({
    "http_error",
    "empty_content",
    "timeout",
    "credit_exhausted",
    "jev_none",
    "provider_raises",
    "malformed_json",
})

# El regex de produccion (`re.search`) casa dentro de una palabra; el estricto
# exige limites de token. Un veredicto solo se acepta si AMBOS coinciden.
PRODUCTION_VERDICT_RE = re.compile(r"(bullish|bearish|neutral)")
STRICT_VERDICT_RE = re.compile(r"\b(bullish|bearish|neutral)\b")
# Regex identico al de evals/gates.py: reutilizado, no reimplementado.
_NUMBER_RE = re.compile(r"-?\d[\d.,]*")
_FENCED_BLOCK = re.compile(r"```[^\r\n]*\r?\n?(.*?)```", re.DOTALL)

# Subarboles que NO son prosa: identificadores y metadatos. Sus digitos son
# identificadores (chunk_id, anio fiscal, confianza), no hechos financieros.
_NON_PROSE_KEYS = frozenset({
    "id",
    "metric_key",
    "section_id",
    "section_ids",
    "ticker",
    "period",
    "citations",
    "citation",
    "evidence_ids",
    "input_chunk_ids",
    "allowed_metric_keys",
    "allowed_section_ids",
    "allowed_labels",
    "tolerated_numbers",
    "answer_source",
    "provider",
    "output_origin",
    "chunk_id",
    "fiscal_year",
    "fiscal_quarter",
})
# Indices y ordinales pequenos: no son hechos financieros (mismo criterio que
# evals/gates.py::_is_tolerance_value).
_TOLERANCE_VALUES = frozenset({0.0, 1.0, 2.0, 3.0})


# ---------------------------------------------------------------------------
# Guardian de red
# ---------------------------------------------------------------------------

_LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost", "0.0.0.0"})


@contextmanager
def no_network() -> Iterator[None]:
    """Bloquea `socket.socket.connect`; loopback sigue permitido.

    El judge no necesita red para nada. Si algun dia un import arrastrado
    intentara abrirla, el eval revienta con un AssertionError en vez de
    colarse en un CI sin credenciales.
    """

    original = socket.socket.connect

    def _guarded(self: socket.socket, address: Any, *args: Any, **kwargs: Any) -> Any:
        host = address[0] if isinstance(address, tuple) else str(address)
        if str(host) in _LOOPBACK:
            return original(self, address, *args, **kwargs)
        raise AssertionError(f"el judge no puede abrir red hacia {host!r}")

    socket.socket.connect = _guarded  # type: ignore[method-assign]
    try:
        yield
    finally:
        socket.socket.connect = original  # type: ignore[method-assign]


# ---------------------------------------------------------------------------
# Objetivo 1: schema / parse
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ParsedOutput:
    """Lo que la capa recibiria del proveedor, ya parseado."""

    present: bool
    payload: Any
    problems: tuple[str, ...]


def _loads(text: str) -> Any:
    """Espejo local de `app.llm.json.parse_json_response` (mismos candidatos)."""
    stripped = text.strip()
    candidates = [stripped]
    candidates.extend(match.group(1).strip() for match in _FENCED_BLOCK.finditer(stripped))
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
    decoder = json.JSONDecoder()
    for index, character in enumerate(stripped):
        if character not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(stripped[index:])
        except json.JSONDecodeError:
            continue
        return value
    raise ValueError("el modelo no devolvio JSON")


def _type_name(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    if value is None:
        return "null"
    return type(value).__name__


def _check_item(item: Any, keys: tuple[str, ...], path: str) -> list[str]:
    if not isinstance(item, dict):
        return [f"{path} no es object sino {_type_name(item)}"]
    problems = [
        f"falta {key}" for key in keys if key not in item
    ]
    problems += [
        f"{key} no permitido (additionalProperties: false)"
        for key in item
        if key not in keys
    ]
    return problems


def parse_output(case: dict) -> ParsedOutput:
    """Objetivo 1. Ausente = no omitible; `None` + fallo declarado = sin salida."""
    if "model_output" not in case:
        return ParsedOutput(
            present=False,
            payload=None,
            problems=("falta model_output: el gate no puede omitirse",),
        )
    raw = case["model_output"]
    if raw is None:
        # Forma de fallo del proveedor: no hay nada que juzgar. La honestidad de
        # esa forma la mide provider_failure_is_degraded_not_answered.
        if not isinstance(case.get("provider"), dict):
            return ParsedOutput(
                present=False,
                payload=None,
                problems=("model_output null sin 'provider' que declare el fallo",),
            )
        return ParsedOutput(present=False, payload=None, problems=())
    if isinstance(raw, str):
        try:
            raw = _loads(raw)
        except ValueError as exc:
            return ParsedOutput(present=True, payload=None, problems=(str(exc),))
    layer = case.get("layer")
    if layer not in LAYERS:
        return ParsedOutput(
            present=True, payload=raw, problems=(f"capa desconocida: {layer!r}",)
        )
    problems: list[str] = []
    if not isinstance(raw, dict):
        return ParsedOutput(
            present=True,
            payload=raw,
            problems=(f"la salida no es object sino {_type_name(raw)}",),
        )
    if layer == "debate":
        problems += _check_item(raw, DEBATE_KEYS, "model_output")
        for key in DEBATE_KEYS:
            if key in raw and (not isinstance(raw[key], str) or not raw[key].strip()):
                problems.append(f"{key} no es texto no vacio")
        return ParsedOutput(present=True, payload=raw, problems=tuple(problems))

    root_key = LAYER_ROOT_KEY[layer]
    if root_key not in raw:
        return ParsedOutput(
            present=True, payload=raw, problems=(f"falta {root_key}",)
        )
    collection = raw[root_key]
    item_keys = LAYER_ITEM_KEYS[layer]
    if layer == "narrative":
        if not isinstance(collection, list):
            return ParsedOutput(
                present=True, payload=raw, problems=("section_ids no es array",)
            )
        if not 1 <= len(collection) <= 8:
            problems.append(f"section_ids fuera de rango: {len(collection)} (1..8)")
        problems += [
            f"section_ids[{index}] no es string"
            for index, item in enumerate(collection)
            if not isinstance(item, str)
        ]
        return ParsedOutput(present=True, payload=raw, problems=tuple(problems))

    if not isinstance(collection, list):
        return ParsedOutput(
            present=True,
            payload=raw,
            problems=(f"{root_key} no es array sino {_type_name(collection)}",),
        )
    for index, item in enumerate(collection):
        path = f"{root_key}[{index}]"
        problems += _check_item(item, item_keys, path)
        if not isinstance(item, dict):
            continue
        for key in item_keys:
            if key in item and _expected_type(key) and not isinstance(
                item[key], _expected_type(key)
            ):
                problems.append(f"{path}.{key} no es {_expected_type(key).__name__}")
        # El RANGO de `confidence` no se comprueba aqui: lo posee la puerta
        # `confidence_in_range`, y que una sola puerta sea la que muerda es lo
        # que permite que un control negativo falle exactamente una.
        if layer == "kpi_extraction" and item.get("fiscal_quarter") not in FISCAL_QUARTERS:
            problems.append(
                f"{path}.fiscal_quarter fuera de enum: {item.get('fiscal_quarter')!r}"
            )
    return ParsedOutput(present=True, payload=raw, problems=tuple(problems))


def _expected_type(key: str) -> type | tuple[type, ...] | None:
    return {
        "metric_key": str,
        "raw_label": str,
        "raw_value": str,
        "raw_unit": str,
        "period": str,
        "fiscal_year": int,
        "fiscal_quarter": str,
        "chunk_id": int,
        "quote": str,
        "confidence": (int, float),
        "principle": str,
        "category": str,
        "application_conditions": list,
        "exceptions": list,
        "company_tickers": list,
        "exact_fragment": str,
    }.get(key)


def _confidence_problems(value: Any, path: str) -> list[str]:
    """`math.isfinite` + rango, igual que jev_choice_or_none."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return [f"{path} no es numero"]
    if not math.isfinite(float(value)):
        return [f"{path} no es finito: {value!r}"]
    if not 0 <= float(value) <= 1:
        return [f"{path} fuera de [0,1]: {value!r}"]
    return []


# ---------------------------------------------------------------------------
# Objetivo 2: fidelidad al grounding
# ---------------------------------------------------------------------------


def _frozen_pool(case: dict) -> set[float]:
    pool: set[float] = set()
    sources = list((case.get("frozen_facts") or {}).values())
    sources += list((case.get("expected") or {}).get("tolerated_numbers") or [])
    for value in sources:
        number = _norm_number(str(value))
        if number is not None:
            pool.add(number)
    return pool


def _walk_strings(value: Any, path: str = "") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _NON_PROSE_KEYS:
                continue
            child = f"{path}.{key}" if path else str(key)
            found += _walk_strings(item, child)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found += _walk_strings(item, f"{path}[{index}]")
    elif isinstance(value, str):
        found.append((path or "root", value))
    return found


def check_grounding(case: dict) -> list[str]:
    """Objetivo 2. Toda cifra citada debe estar en los frozen_facts."""
    if "frozen_facts" not in case:
        return ["falta frozen_facts: el gate no puede omitirse"]
    pool = _frozen_pool(case)
    if not pool:
        return ["frozen_facts no aporta ninguna cifra utilizable: el gate no puede omitirse"]
    problems: list[str] = []
    for origin, payload in (
        ("model_output", case.get("model_output")),
        ("layer_output", case.get("layer_output")),
    ):
        for path, text in _walk_strings(payload):
            for token in _NUMBER_RE.findall(text):
                number = _norm_number(token)
                if number is None or number in _TOLERANCE_VALUES or number in pool:
                    continue
                problems.append(
                    f"cifra sin frozen fact en {origin}{path}: {token} -> {number}"
                )
    return problems


# ---------------------------------------------------------------------------
# Objetivo 3: coherencia estructural
# ---------------------------------------------------------------------------


def _confidences(case: dict) -> list[tuple[str, Any]]:
    rows: list[tuple[str, Any]] = []
    raw = case.get("model_output")
    if isinstance(raw, dict):
        root_key = LAYER_ROOT_KEY.get(str(case.get("layer")))
        collection = raw.get(root_key) if root_key else None
        if isinstance(collection, list):
            for index, item in enumerate(collection):
                if isinstance(item, dict) and "confidence" in item:
                    rows.append((f"{root_key}[{index}].confidence", item["confidence"]))
        if "confidence" in raw:
            rows.append(("model_output.confidence", raw["confidence"]))
    layer_output = case.get("layer_output")
    if isinstance(layer_output, dict) and "confidence" in layer_output:
        rows.append(("layer_output.confidence", layer_output["confidence"]))
    return rows


def check_confidences(case: dict) -> list[str]:
    rows = _confidences(case)
    if not rows:
        return []
    problems: list[str] = []
    for path, value in rows:
        problems += _confidence_problems(value, path)
    return problems


def production_verdict(text: str) -> str | None:
    """Regex de produccion: casa dentro de la palabra (p.ej. "bullishness")."""
    match = PRODUCTION_VERDICT_RE.search((text or "").lower())
    return match.group(1) if match else None


def strict_verdict(text: str) -> str | None:
    match = STRICT_VERDICT_RE.search((text or "").lower())
    return match.group(1) if match else None


def check_labels(case: dict) -> list[str]:
    """Etiquetas desconocidas, enums de metric_key/category/section_id, veredicto."""
    problems: list[str] = []
    layer = case.get("layer")
    raw = case.get("model_output")
    if isinstance(raw, dict) and layer in {"kpi_extraction", "principles"}:
        root_key = LAYER_ROOT_KEY[layer]
        collection = raw.get(root_key)
        allowed_key = "allowed_metric_keys" if layer == "kpi_extraction" else "allowed_labels"
        allowed = case.get(allowed_key)
        if allowed is None:
            problems.append(f"el caso no declara {allowed_key}: el gate no puede omitirse")
            allowed = []
        if isinstance(collection, list):
            for index, item in enumerate(collection):
                if not isinstance(item, dict):
                    continue
                value = item.get("metric_key" if layer == "kpi_extraction" else "category")
                if value is None:
                    continue
                if layer == "principles" and value not in PRINCIPLE_CATEGORIES:
                    problems.append(
                        f"{root_key}[{index}] fuera del vocabulario cerrado de "
                        f"categorias: {value!r}"
                    )
                elif value not in allowed:
                    problems.append(f"{root_key}[{index}] etiqueta desconocida: {value!r}")
    if layer == "narrative" and isinstance(raw, dict):
        allowed_sections = case.get("allowed_section_ids")
        if allowed_sections is None:
            problems.append("el caso no declara allowed_section_ids: el gate no puede omitirse")
            allowed_sections = []
        for index, section_id in enumerate(raw.get("section_ids") or []):
            if isinstance(section_id, str) and section_id not in allowed_sections:
                problems.append(f"section_ids[{index}] etiqueta desconocida: {section_id!r}")
    if layer == "debate":
        answer_source = (case.get("layer_output") or {}).get("answer_source")
        if answer_source is not None and answer_source not in ANSWER_SOURCES:
            problems.append(f"answer_source fuera de enum: {answer_source!r}")
        judge_text = raw.get("judge_text") if isinstance(raw, dict) else None
        if isinstance(judge_text, str) and judge_text.strip():
            loose = production_verdict(judge_text)
            strict = strict_verdict(judge_text)
            if loose is None:
                # Sin etiqueta solo hay defecto si la capa pretende que el modelo
                # fallo de verdad. Si `answer_source` ya declara un fallback,
                # la ausencia de etiqueta es la CAUSA del fallback, no el fallo.
                if answer_source in MODEL_ANSWER_SOURCES:
                    problems.append("el juez no emite ninguna etiqueta del conjunto permitido")
            elif loose != strict:
                problems.append(
                    "etiqueta no reconocida como token independiente: "
                    f"el regex de produccion casa {loose!r}, los limites de token no"
                )
            elif loose not in DEBATE_VERDICT_LABELS:
                problems.append(f"etiqueta fuera de {list(DEBATE_VERDICT_LABELS)}: {loose!r}")
    return problems


def check_verdict_allowed(case: dict) -> list[str]:
    layer_output = case.get("layer_output")
    if case.get("layer") != "debate" or not isinstance(layer_output, dict):
        return []
    if "verdict" not in layer_output:
        return ["falta layer_output.verdict: el gate no puede omitirse"]
    verdict = layer_output["verdict"]
    if verdict is None:
        return [] if _may_abstain(case) else ["verdict ausente sin abstension declarada"]
    if verdict not in DEBATE_VERDICT_LABELS:
        return [f"veredicto {verdict!r} fuera de {list(DEBATE_VERDICT_LABELS)}"]
    return []


def _may_abstain(case: dict) -> bool:
    expected = case.get("expected") or {}
    return bool(expected.get("abstain")) or bool(expected.get("degraded"))


def check_probabilities(case: dict) -> list[str]:
    layer_output = case.get("layer_output")
    if not isinstance(layer_output, dict):
        return ["falta layer_output: el gate no puede omitirse"]
    scenarios = layer_output.get("scenario_probabilities")
    if not scenarios:
        return [
            "el artefacto no trae scenario_probabilities: el gate no puede omitirse"
        ]
    if not isinstance(scenarios, dict):
        return ["scenario_probabilities no es dict"]
    total = 0.0
    problems: list[str] = []
    for key in sorted(scenarios):
        value = scenarios[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            problems.append(f"scenario_probabilities.{key} no es numero")
            continue
        if not math.isfinite(float(value)):
            problems.append(f"scenario_probabilities.{key} no es finito: {value!r}")
            continue
        if not 0 <= float(value) <= 1:
            problems.append(f"scenario_probabilities.{key} fuera de [0,1]: {value!r}")
        total += float(value)
    if not problems and abs(total - 1.0) > 0.01:
        problems.append(f"suma={total:.4f} (esperado 1.0 +/- 0.01)")
    return problems


def check_scenario_ordering(case: dict) -> list[str]:
    """`bear <= bull <= base`: el escenario base es el mas probable.

    Un `bear` por encima del `bull` es una contradiccion interna (la tesis
    seria mas probable en su escenario adverso que en el favorable) y es
    justo lo que el gate existe para cazar.
    """
    scenarios = (case.get("layer_output") or {}).get("scenario_probabilities")
    if not isinstance(scenarios, dict):
        return ["falta scenario_probabilities: el gate no puede omitirse"]
    missing = [key for key in ("bear", "base", "bull") if key not in scenarios]
    if missing:
        return [f"faltan escenarios: {missing}"]
    bear = scenarios["bear"]
    base = scenarios["base"]
    bull = scenarios["bull"]
    for name, value in (("bear", bear), ("base", base), ("bull", bull)):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return [f"scenario_probabilities.{name} no es numero"]
    if not bear <= bull <= base:
        return [f"ordenacion bear<=bull<=base rota: {bear}/{bull}/{base}"]
    return []


def _evidence_ids(case: dict) -> set[str]:
    evidence = (case.get("layer_output") or {}).get("evidence") or []
    return {
        str(item.get("id"))
        for item in evidence
        if isinstance(item, dict) and item.get("id") is not None
    }


def _published_answer(case: dict) -> str:
    """Que ha publicado la capa; cadena corta para los detalles del gate."""
    layer = case.get("layer")
    raw = case.get("model_output")
    layer_output = case.get("layer_output") or {}
    if layer == "debate":
        return f"verdict={layer_output.get('verdict')!r}"
    if isinstance(raw, dict):
        root_key = LAYER_ROOT_KEY.get(str(layer))
        collection = raw.get(root_key) if root_key else None
        if isinstance(collection, list):
            return f"{len(collection)} {root_key}"
    return "contenido substantivo"


def check_claims_evidence(case: dict) -> list[str]:
    problems: list[str] = []
    layer = case.get("layer")
    layer_output = case.get("layer_output") or {}
    known = _evidence_ids(case)
    claims = layer_output.get("claims") or []
    if not isinstance(claims, list):
        return ["layer_output.claims no es array"]
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict) or not claim.get("material", True):
            continue
        linked = [eid for eid in claim.get("evidence_ids") or [] if str(eid) in known]
        if not linked:
            problems.append(f"claim material sin evidencia: {str(claim.get('text'))[:60]}")
    if layer == "principles":
        problems += _check_fragments(case)
    if layer == "narrative":
        problems += _check_narrative_citations(layer_output, known)
    if layer == "kpi_extraction":
        chunk_ids = case.get("input_chunk_ids")
        raw = case.get("model_output")
        collection = raw.get("observations") if isinstance(raw, dict) else None
        if isinstance(chunk_ids, list) and isinstance(collection, list):
            allowed = {int(cid) for cid in chunk_ids}
            for index, item in enumerate(collection):
                if not isinstance(item, dict):
                    continue
                chunk_id = item.get("chunk_id")
                if isinstance(chunk_id, int) and chunk_id not in allowed:
                    problems.append(
                        f"observations[{index}].chunk_id {chunk_id} no esta en la entrada"
                    )
    return problems


def _check_fragments(case: dict) -> list[str]:
    """`exact_fragment` debe ser verbatim dentro del texto que entro al LLM."""
    raw = case.get("model_output")
    collection = raw.get("principles") if isinstance(raw, dict) else None
    if not isinstance(collection, list):
        return []
    source = str(case.get("input") or "")
    if not source:
        return ["el caso no declara input: el gate no puede omitirse"]
    problems: list[str] = []
    for index, item in enumerate(collection):
        if not isinstance(item, dict):
            continue
        fragment = item.get("exact_fragment")
        if not isinstance(fragment, str) or not fragment.strip():
            problems.append(f"principles[{index}].exact_fragment vacio")
        elif fragment not in source:
            problems.append(
                f"principles[{index}] cita una fuente que no esta en la entrada: "
                f"{fragment[:60]!r}"
            )
    return problems


def _check_narrative_citations(layer_output: dict, known: set[str]) -> list[str]:
    sections = layer_output.get("sections") or []
    if not isinstance(sections, list):
        return ["layer_output.sections no es array"]
    problems: list[str] = []
    for index, section in enumerate(sections):
        if not isinstance(section, dict):
            continue
        paragraphs = " ".join(str(p) for p in section.get("paragraphs") or [])
        cites_number = bool(_NUMBER_RE.search(paragraphs))
        citations = [str(c) for c in section.get("citations") or []]
        if cites_number and not citations:
            problems.append(
                f"sections[{index}] cita una cifra sin ninguna fuente: "
                f"{str(section.get('section_id'))[:40]}"
            )
        elif citations and not any(cid in known for cid in citations):
            problems.append(
                f"sections[{index}] cita una fuente inexistente: {citations[:3]}"
            )
    return problems


def check_degraded_honesty(case: dict) -> list[str]:
    """La puerta que mas importa: distinguir "no lo se" de "lo se".

    Reglas, en este orden y sin atajos:

    - ``expected.degraded`` debe declararse; si no, la puerta esta anulada.
    - ``layer_output.degraded`` debe coincidir con lo esperado y ser booleano.
    - Si HAY fallo: la forma del fallo se declara y se conoce, la respuesta no
      viene de un juez del modelo, no publica confianza calibrada, y un
      veredicto determinista revela que el juez no estaba disponible.
    - Si NO hay fallo: la respuesta no puede venir de una fuente degradada, y
      si no hay ``model_output`` tampoco puede haber una respuesta normal: o el
      caso se abstiene, o declara la degradacion.
    """
    expected = case.get("expected") or {}
    if "degraded" not in expected:
        return ["el caso no declara expected.degraded: el gate no puede omitirse"]
    layer_output = case.get("layer_output")
    if not isinstance(layer_output, dict):
        return ["falta layer_output: el gate no puede omitirse"]
    if "degraded" not in layer_output:
        return ["falta layer_output.degraded: el gate no puede omitirse"]
    want = bool(expected["degraded"])
    is_degraded = layer_output["degraded"]
    if not isinstance(is_degraded, bool):
        return [f"layer_output.degraded no es boolean: {is_degraded!r}"]
    if is_degraded != want:
        return [f"degraded {is_degraded} != esperado {want}"]
    answer_source = layer_output.get("answer_source")
    abstained = bool(layer_output.get("abstained"))
    if not want:
        if answer_source in DEGRADED_ANSWER_SOURCES:
            return [
                f"degraded=false pero answer_source={answer_source!r} es una fuente degradada"
            ]
        if case.get("model_output") is None and not abstained:
            return [
                "sin model_output y degraded=false: la respuesta no tiene origen "
                "declarado, o no es una respuesta"
            ]
        return []
    provider = case.get("provider")
    if not isinstance(provider, dict):
        return ["expected.degraded=true pero el caso no declara provider"]
    failure = provider.get("failure")
    skipped = provider.get("skipped")
    if not failure and not skipped:
        return [
            "expected.degraded=true pero el caso no declara ni provider.failure "
            "ni provider.skipped: no se sabe por que se degrado"
        ]
    if failure is not None and failure not in PROVIDER_FAILURE_SHAPES:
        return [
            f"forma de fallo desconocida: {failure!r} "
            f"(permitidas: {sorted(PROVIDER_FAILURE_SHAPES)})"
        ]
    if answer_source is None:
        return ["expected.degraded=true pero la capa no declara answer_source"]
    if answer_source in MODEL_ANSWER_SOURCES:
        return [
            "un fallo del proveedor se presenta como respuesta del modelo: "
            f"answer_source={answer_source!r}"
        ]
    if answer_source not in DEGRADED_ANSWER_SOURCES:
        return [f"answer_source {answer_source!r} no declara degradacion"]
    if "confidence" in layer_output:
        return [
            "un fallback publica confianza calibrada: no lo se no es un numero "
            f"({layer_output['confidence']!r})"
        ]
    if answer_source == "deterministic_fallback":
        rationale = str(
            layer_output.get("verdict_rationale") or layer_output.get("caveat") or ""
        )
        if not any(marker in rationale.lower() for marker in DEGRADED_DISCLOSURE_MARKERS):
            return [
                "el veredicto determinista no revela que el juez no estaba "
                f"disponible: {rationale[:80]!r}"
            ]
    if answer_source == "abstained" and not abstained:
        return [f"answer_source=abstained pero abstained={abstained!r}"]
    return []


def check_abstention(case: dict) -> list[str]:
    """La capa debe callar cuando la evidencia no da, y hablar cuando si."""
    expected = case.get("expected") or {}
    if "abstain" not in expected:
        return ["el caso no declara expected.abstain: el gate no puede omitirse"]
    layer_output = case.get("layer_output")
    if not isinstance(layer_output, dict):
        return ["falta layer_output: el gate no puede omitirse"]
    want = bool(expected["abstain"])
    abstained = layer_output.get("abstained")
    if not isinstance(abstained, bool):
        return [f"falta layer_output.abstained booleano: {abstained!r}"]
    if want and not abstained:
        return ["la capa debia abstenerse y respondio"]
    if want:
        raw = case.get("model_output")
        root_key = LAYER_ROOT_KEY.get(str(case.get("layer")))
        collection = raw.get(root_key) if isinstance(raw, dict) and root_key else None
        if isinstance(collection, list) and collection:
            return [f"la capa debia abstenerse y publico {_published_answer(case)}"]
        if case.get("layer") == "debate" and layer_output.get("verdict") is not None:
            return [f"la capa debia abstenerse y emitió {layer_output['verdict']!r}"]
    if not want and abstained:
        return ["la capa se abstuvo con evidencia suficiente"]
    return []


# ---------------------------------------------------------------------------
# Informe completo: los tres objetivos en un solo objeto
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class JudgeReport:
    case: str
    layer: str
    category: str
    schema: tuple[str, ...]
    grounding: tuple[str, ...]
    structure: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "case": self.case,
            "layer": self.layer,
            "category": self.category,
            "schema": list(self.schema),
            "grounding": list(self.grounding),
            "structure": list(self.structure),
            "verdict": "pass" if self.ok else "fail",
        }

    @property
    def ok(self) -> bool:
        return not (self.schema or self.grounding or self.structure)


def judge_case(case: dict) -> JudgeReport:
    """Determinista y sin estado: dos llamadas ⇒ el mismo dict byte a byte."""
    parsed = parse_output(case)
    structure = [
        problem
        for problem in (
            *check_confidences(case),
            *check_labels(case),
            *check_probabilities(case),
            *check_scenario_ordering(case),
            *check_claims_evidence(case),
            *check_verdict_allowed(case),
            *check_degraded_honesty(case),
            *check_abstention(case),
        )
    ]
    return JudgeReport(
        case=str(case.get("id") or ""),
        layer=str(case.get("layer") or ""),
        category=str(case.get("category") or ""),
        schema=tuple(sorted(parsed.problems)),
        grounding=tuple(sorted(check_grounding(case))),
        structure=tuple(sorted(structure)),
    )