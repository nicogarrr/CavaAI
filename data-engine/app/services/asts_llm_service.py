"""Natural-language LLM analysis of the persisted CelesTrak AST catalog.

Data discipline: the DETERMINISTIC summary is always the canonical response
text — it restates only the real persisted snapshot and is never replaced.
A passed generative call adds a separate `llm_interpretation` section,
explicitly labeled unverified, and only after a hygiene check that every
number, object name and date it cites exists in the snapshot (bag check,
not semantic proof). 'sin datos' whenever the snapshot is stale (>30h) or
missing — in that case no LLM call happens and no quota is consumed. The
generative path is operator-gated (ASTS_LLM_ENABLED=1), limited to the
verified free model and budgeted per tenant by asts_llm_quota.
"""

from __future__ import annotations

import json
import os
import re
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
    # llm_interpretation: seccion aparte que solo rellena una llamada
    # generativa superada; nunca sustituye este resumen canonico.
    return {"summary": summary, "observations": observations, "aggregates": agg,
            "llm_interpretation": None}


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


_NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?(?![\w.])")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?)?")
_NAME_RE = re.compile(r"\b(?:BLUEWALKER|SPACEMOBILE)-\d+\b")
_FAMILY_RE = re.compile(r"\b(BLUEWALKER|SPACEMOBILE)\b(?![-\d])")


def _real_values(satellites: list[dict], agg: dict) -> list[float]:
    values: list[float] = []
    for sat in satellites:
        values.extend([float(sat["norad_cat_id"]), sat["inclination"],
                       sat["mean_motion"], sat["eccentricity"]])
    values.extend([float(agg["count"]), *(float(v) for v in agg["families"].values()),
                   agg["inclination_deg_min"], agg["inclination_deg_max"],
                   agg["mean_motion_rev_day_min"], agg["mean_motion_rev_day_max"],
                   agg["eccentricity_max"]])
    return values


def _number_ok(token: str, reals: list[float], years: set[int]) -> bool:
    value = float(token.replace(",", "."))
    if token.replace(",", "").isdigit() and 1900 <= value <= 2100:
        # Un año suelto solo es valido si es el año de algun dato real.
        return int(value) in years
    decimals = len(token.replace(",", ".").split(".")[1]) if ("." in token or "," in token) else 0
    tolerance = 0.5 * 10 ** -decimals + 1e-12
    return any(abs(real - value) <= tolerance for real in reals)


def _llm_text_verified(analysis: AstsAnalysis, satellites: list[dict], agg: dict,
                       fetched_at: str) -> bool:
    """Every number, object name and date in the LLM text must exist in the
    persisted snapshot (rounding-tolerant for magnitudes); the summary must
    name CelesTrak and the real fetch day. Anything unverifiable rejects the
    whole generative text: the deterministic summary is the canonical answer.
    It does not prove prose semantics — declared limit.
    """
    if "celestrak" not in analysis.summary.lower():
        return False
    if fetched_at[:10] not in analysis.summary:
        return False
    texts = " ".join([analysis.summary, *(obs.text for obs in analysis.observations)])
    real_names = {sat["object_name"] for sat in satellites}
    if any(name not in real_names for name in _NAME_RE.findall(texts)):
        return False
    if any(family not in agg["families"] for family in _FAMILY_RE.findall(texts)):
        return False
    timestamps = [fetched_at, *(sat["epoch"] for sat in satellites)]
    masked = texts
    for match in _DATE_RE.findall(texts):
        token = match
        day_ok = any(ts[:10] == token[:10] for ts in timestamps)
        time_ok = len(token) == 10 or any(
            ts.startswith(token.replace(" ", "T")) for ts in timestamps)
        if not (day_ok and time_ok):
            return False
        masked = masked.replace(token, " ", 1)
    reals = _real_values(satellites, agg)
    years = {int(ts[:4]) for ts in timestamps}
    return all(_number_ok(token, reals, years) for token in _NUMBER_RE.findall(masked))


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
                    if _llm_text_verified(extraction, snapshot["satellites"], agg,
                                          snapshot["fetched_at"]):
                        # Seccion aparte, nunca sustituye al resumen canonico.
                        analysis["llm_interpretation"] = {
                            "summary": extraction.summary,
                            "observations": [obs.model_dump() for obs in extraction.observations],
                            "disclaimer": (
                                "Interpretación generativa no verificada: la lectura "
                                "puede ser incorrecta aunque las cifras citadas existan "
                                "en el catálogo. El resumen canónico es el determinista."),
                        }
                        mode = "llm"
                    else:
                        note = ("Interpretación generativa descartada: incluía datos "
                                "no contrastados con el catálogo.")
            except Exception:  # noqa: BLE001 - never claim a failed call worked
                note = "Análisis LLM no disponible; se usa el resumen determinista."
    return {
        **base, "status": "disponible", "mode": mode, "analysis": analysis,
        "llm_quota": llm_quota, "llm_input": llm_input, "note": note,
    }
