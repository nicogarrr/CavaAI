"""Natural-language LLM analysis of the persisted CelesTrak AST catalog.

Data discipline: the analysis may only restate the real persisted snapshot.
The deterministic path aggregates the same rows with no generative step and
is always included. 'sin datos' whenever the snapshot is stale (>30h) or
missing — in that case no LLM call happens and no quota is consumed. The
generative path is operator-gated (ASTS_LLM_ENABLED=1), limited to the
verified free model and budgeted per tenant by asts_llm_quota.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.llm import LLMRequest, Message, ResponseFormat, create_llm_provider, parse_json_response
from app.services.asts_catalog_service import read_catalog
from app.services.asts_llm_quota import reserve_llm_call
from app.services.async_bridge import run_from_any_context
from app.services.connectors.celestrak_ast import SOURCE_URL

MAX_LLM_SATELLITES = 150


class Observation(BaseModel):
    text: str = Field(max_length=240)


class AstsAnalysis(BaseModel):
    summary: str = Field(max_length=600)
    observations: list[Observation] = Field(max_length=8)


_SCHEMA = AstsAnalysis.model_json_schema()


def _aggregates(satellites: list[dict]) -> dict:
    epochs = sorted(s["epoch"] for s in satellites)
    inclinations = [s["inclination"] for s in satellites]
    motions = [s["mean_motion"] for s in satellites]
    eccentricities = [s["eccentricity"] for s in satellites]
    families: dict[str, int] = {}
    for sat in satellites:
        family = "BLUEWALKER" if sat["object_name"] == "BLUEWALKER-3" else "SPACEMOBILE"
        families[family] = families.get(family, 0) + 1
    return {
        "count": len(satellites),
        "families": families,
        "epoch_min": epochs[0], "epoch_max": epochs[-1],
        "inclination_deg_min": round(min(inclinations), 4),
        "inclination_deg_max": round(max(inclinations), 4),
        "mean_motion_rev_day_min": round(min(motions), 4),
        "mean_motion_rev_day_max": round(max(motions), 4),
        "eccentricity_max": round(max(eccentricities), 6),
    }


def _deterministic_analysis(agg: dict, fetched_at: str) -> dict:
    families = ", ".join(f"{count} {name}" for name, count in sorted(agg["families"].items()))
    summary = (
        f"Catálogo CelesTrak del grupo AST descargado el {fetched_at}: "
        f"{agg['count']} objetos ({families}). Épocas orbitales entre "
        f"{agg['epoch_min']} y {agg['epoch_max']}. Inclinación entre "
        f"{agg['inclination_deg_min']}° y {agg['inclination_deg_max']}°, "
        f"movimiento medio entre {agg['mean_motion_rev_day_min']} y "
        f"{agg['mean_motion_rev_day_max']} rev/día, excentricidad máxima "
        f"{agg['eccentricity_max']}."
    )
    observations = [
        {"text": f"Familias del catálogo: {families}."},
        {"text": f"Época orbital más reciente: {agg['epoch_max']}; más antigua: {agg['epoch_min']}."},
        {"text": (f"Inclinación entre {agg['inclination_deg_min']}° y "
                  f"{agg['inclination_deg_max']}°; movimiento medio entre "
                  f"{agg['mean_motion_rev_day_min']} y {agg['mean_motion_rev_day_max']} rev/día.")},
    ]
    return {"summary": summary, "observations": observations, "aggregates": agg}


def _llm_payload(satellites: list[dict], agg: dict, fetched_at: str) -> tuple[str, str]:
    base = {
        "fuente": "CelesTrak, grupo AST", "url_fuente": SOURCE_URL,
        "descargado_en": fetched_at,
        "aviso": ("La frescura es la de la última descarga; el EPOCH orbital de "
                  "cada objeto puede ser anterior. No son posiciones actuales."),
        "agregados": agg,
    }
    if len(satellites) <= MAX_LLM_SATELLITES:
        base["satelites"] = [
            {"nombre": s["object_name"], "epoch": s["epoch"],
             "inclinacion_deg": s["inclination"], "movimiento_medio_rev_dia": s["mean_motion"],
             "excentricidad": s["eccentricity"]}
            for s in satellites
        ]
        mode = "completo"
    else:
        base["nota"] = (f"Catálogo de {len(satellites)} objetos: se envían solo los "
                        "agregados por límite de contexto. No inventes filas.")
        mode = "agregado"
    return json.dumps(base, ensure_ascii=False), mode


async def _analyze_with_llm(payload: str) -> tuple[AstsAnalysis, object]:
    provider = create_llm_provider()
    if provider.name == "disabled":
        raise RuntimeError("LLM not configured")
    request = LLMRequest(
        messages=[
            Message("system", (
                "Analiza en español el catálogo satelital del grupo AST proporcionado. "
                "Usa SOLO los datos del mensaje: no inventes satélites, valores ni "
                "efemérides. Cada observación debe citar valores concretos del catálogo "
                "(nombres, épocas, rangos). Menciona en el resumen que la fuente es "
                "CelesTrak e incluye la fecha de descarga. No afirmes posiciones "
                "actuales, mapas ni trayectorias: la frescura es la de la última "
                "descarga y el EPOCH orbital puede ser anterior. No des consejo de "
                "inversión. Responde solo JSON."
            )),
            Message("user", payload),
        ],
        task="asts_catalog_analysis",
        model="space-bunny-free",
        temperature=0,
        max_tokens=900,
        response_format=ResponseFormat.json_schema(_SCHEMA, name="asts_catalog_analysis"),
    )
    # Pin the exact free model: task overrides and env defaults may route to paid models.
    if provider.model_router.resolve(request) != "space-bunny-free":
        raise RuntimeError("ASTS catalog model is not the verified free model")
    response = await provider.complete(request)
    return AstsAnalysis.model_validate(parse_json_response(response.text)), response


def analyze_asts_catalog(db: Session, *, use_llm: bool = True) -> dict:
    """Read-only except the LLM quota reservation; never mutates the catalog."""
    snapshot = read_catalog(db)  # tenant-scoped; raises without tenant context
    source = {
        "name": "celestrak", "url": SOURCE_URL,
        "fetched_at": snapshot["fetched_at"],
        "freshness_basis": snapshot["freshness_basis"],
    }
    base = {
        "ticker": "ASTS", "generated_at": datetime.now(UTC).isoformat(),
        "source": source, "usage_note": snapshot["usage_note"],
        "warning": ("Resumen descriptivo del catálogo descargado; no verifica "
                    "posiciones actuales ni constituye recomendación de inversión."),
    }
    if snapshot["status"] != "disponible":
        return {
            **base, "status": "sin datos", "mode": None, "analysis": None,
            "llm_quota": None,
            "stale_snapshot_at": snapshot["stale_snapshot_at"],
            "note": ("Sin datos frescos: no hay catálogo persistido o la última "
                     "descarga supera 30 h. No se ha llamado al modelo."),
        }
    agg = _aggregates(snapshot["satellites"])
    analysis = _deterministic_analysis(agg, snapshot["fetched_at"])
    mode = "determinista"
    note = None
    llm_quota = None
    llm_input = None
    if use_llm:
        if os.getenv("ASTS_LLM_ENABLED") != "1":
            note = "Análisis LLM desactivado por configuración."
        else:
            try:
                llm_quota = reserve_llm_call(db.info.get("tenant_id"), get_settings())
                if not llm_quota["allowed"]:
                    note = "Análisis LLM no disponible: tope alcanzado."
                else:
                    payload, llm_input = _llm_payload(snapshot["satellites"], agg,
                                                      snapshot["fetched_at"])
                    extraction, _response = run_from_any_context(_analyze_with_llm(payload))
                    analysis = {
                        "summary": extraction.summary,
                        "observations": [obs.model_dump() for obs in extraction.observations],
                        "aggregates": agg,
                    }
                    mode = "llm"
            except Exception:  # noqa: BLE001 - never claim a failed call worked
                note = "Análisis LLM no disponible; se usa el resumen determinista."
    return {
        **base, "status": "disponible", "mode": mode, "analysis": analysis,
        "llm_quota": llm_quota, "llm_input": llm_input, "note": note,
    }
