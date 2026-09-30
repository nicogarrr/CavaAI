"""Procedencia de los inputs de la tesis.

Cada input del modelo se etiqueta como dato / derivado / estimacion_llm /
supuesto, con metodo, cita (fact ids) y confianza. Determinista: traduce lo
que el motor fundamental ya persiste (source_type, basis, source_fact_ids,
confidence) a las etiquetas que ve el usuario. Nunca inventa procedencia:
lo no clasificable (source_type "missing") no se etiqueta; lo lista la
seccion de datos pendientes.
"""

from __future__ import annotations

from typing import Any

LABEL_DATO = "dato"
LABEL_DERIVADO = "derivado"
LABEL_ESTIMACION_LLM = "estimacion_llm"
LABEL_SUPUESTO = "supuesto"

LABELS = (LABEL_DATO, LABEL_DERIVADO, LABEL_ESTIMACION_LLM, LABEL_SUPUESTO)

# Assumptions del modelo: todo lo que el motor calcula a partir de facts es
# un derivado (lleva formula/metodo + inputs); las constantes de politica y
# los supuestos (usuario u override) son supuestos; las estimaciones LLM
# llegan etiquetadas como tales desde su productor.
_ASSUMPTION_LABELS = {
    "financial_facts": LABEL_DERIVADO,
    "calculated_metric": LABEL_DERIVADO,
    "model_policy": LABEL_SUPUESTO,
    "assumption_override": LABEL_SUPUESTO,
    "user_provided": LABEL_SUPUESTO,
    "llm_estimate": LABEL_ESTIMACION_LLM,
}


def label_for_assumption(source_type: str | None) -> str | None:
    """Etiqueta de una assumption del modelo; None = sin dato (pendiente)."""
    if not source_type or source_type == "missing":
        return None
    return _ASSUMPTION_LABELS.get(source_type)


def _item(
    key: str,
    label: str,
    value: Any,
    unit: str | None,
    method: str | None,
    source_fact_ids: list[int],
    confidence: Any,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "value": value,
        "unit": unit,
        "method": method,
        "source_fact_ids": source_fact_ids,
        "confidence": confidence,
    }


def build_inputs_provenance(long_term_model: dict[str, Any]) -> list[dict[str, Any]]:
    """Inputs etiquetados a partir del payload del motor fundamental.

    - assumptions: derivado/supuesto/estimacion_llm segun source_type.
    - driver_model sourced: dato (linea reportada con cita al fact).
    """
    items: list[dict[str, Any]] = []
    assumptions = long_term_model.get("assumptions") or {}
    for key, assumption in sorted(assumptions.items()):
        if not isinstance(assumption, dict):
            continue
        label = label_for_assumption(assumption.get("source_type"))
        if label is None:
            continue
        items.append(
            _item(
                key,
                label,
                assumption.get("value"),
                assumption.get("unit"),
                assumption.get("basis"),
                list(assumption.get("source_fact_ids") or []),
                assumption.get("confidence"),
            )
        )
    for driver in long_term_model.get("driver_model") or []:
        if not isinstance(driver, dict) or driver.get("status") != "sourced":
            continue
        trace = driver.get("trace") or {}
        period = trace.get("period")
        method = f"{driver.get('driver_type', 'driver')} reportado"
        if period:
            method = f"{method} (periodo {period})"
        items.append(
            _item(
                str(driver.get("key")),
                LABEL_DATO,
                driver.get("value"),
                driver.get("unit"),
                method,
                list(driver.get("source_fact_ids") or []),
                driver.get("confidence"),
            )
        )
    return items


def inputs_provenance_from_snapshot(snapshot: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Read-back desde FundamentalModelVersion.model_snapshot persistido."""
    return build_inputs_provenance(snapshot or {})
