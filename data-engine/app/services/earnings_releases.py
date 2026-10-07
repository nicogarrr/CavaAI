"""Free extractive earnings-release summaries. No model, computed figures or calls."""
from __future__ import annotations

import re

from app.services.filing_changes import excerpt_units

_RESULTS = re.compile(r"\b(?:financial results|quarter(?:ly)? results|results for the|earnings release|resultados (?:financieros|trimestrales)|reports? (?:first|second|third|fourth)[- ]quarter)\b", re.I)
_METRIC = re.compile(r"\b(?:revenue|net (?:income|loss)|earnings per share|cash flow|operating (?:income|loss|margin)|ingresos|beneficio neto|flujo de caja)\b", re.I)
_GUIDANCE = re.compile(r"\b(?:guidance|outlook|forecast|previsiones|perspectivas)\b", re.I)
_CHANGE = re.compile(r"\b(?:rais(?:e[ds]?|ing)|lower(?:ed|s|ing)?|reaffirm(?:ed|s)?|withdraw(?:n|s)?|maintain(?:ed|s)?|revis(?:ed|es)|aumenta|reduce|mantiene|retira)\b", re.I)
_BOILERPLATE = re.compile(r"\b(?:forward[- ]looking statements|safe harbor|exhibit\s+99|incorporated (?:herein|by reference)|(?:attached|accompanying) exhibit|declaraciones prospectivas)\b", re.I)


def summarize_release(chunks: list[dict], metadata: dict) -> dict:
    units = excerpt_units(chunks)
    text = "\n".join(u["text"] for u in units)
    form = str(metadata.get("form", "")).upper()
    tied_to_8k = form == "8-K" or (form.startswith("EX-99") and metadata.get("parent_form") == "8-K")
    if not tied_to_8k or not _RESULTS.search(text):
        return {"status": "insufficient_data", "reason": "Sin comunicado de resultados vinculado a un 8-K.",
                "key_points": [], "guidance": []}
    candidates = [u for u in units if 30 <= len(u["text"]) <= 2500 and not _BOILERPLATE.search(u["text"])]
    points = [u for u in candidates if _METRIC.search(u["text"]) and re.search(r"\d", u["text"])]
    guidance = [{**u, "change_status": "explicit_language" if _CHANGE.search(u["text"]) else "not_established"}
                for u in candidates if _GUIDANCE.search(u["text"])]
    if not points and not guidance:
        return {"status": "insufficient_data", "reason": "El 8-K solo remite a un anexo o no contiene resultados legibles.",
                "key_points": [], "guidance": []}
    return {"status": "ready", "method": "extractive", "label": "Extractos originales del comunicado",
            "key_points_label": "Puntos clave", "guidance_label": "Guidance declarado",
            "key_points": points[:6], "guidance": guidance[:6],
            "truncated": len(points) > 6 or len(guidance) > 6,
            "guidance_comparison_status": "not_established",
            "caveat": "Citas en el idioma original. No son transcripciones ni cifras recalculadas. El cambio de guidance solo se señala si el comunicado lo declara."}
