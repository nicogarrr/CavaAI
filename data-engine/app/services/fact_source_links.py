"""Enlaces a la fuente de los supuestos del modelo a largo plazo.

El modelo guarda solo ``source_fact_ids`` (numeros internos que el usuario no
puede abrir). Aqui se resuelven a documentos reales con
``resolve_fact_sources`` (FinancialFact.source_id -> Document), nunca desde lo
declarado por el modelo. Solo se anade ``fuentes``; no se toca nada mas.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.thesis_service import resolve_fact_sources


def attach_assumption_sources(db: Session, company_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    assumptions = payload.get("assumptions")
    if not isinstance(assumptions, dict):
        return payload
    ids = sorted(
        {
            fid
            for item in assumptions.values()
            if isinstance(item, dict)
            for fid in (item.get("source_fact_ids") or [])
            if isinstance(fid, int) and not isinstance(fid, bool)
        }
    )
    sources = resolve_fact_sources(db, company_id, ids)
    for item in assumptions.values():
        if not isinstance(item, dict):
            continue
        seen: set[tuple[str | None, str | None, str | None]] = set()
        fuentes: list[dict[str, Any]] = []
        for fid in item.get("source_fact_ids") or []:
            src = sources.get(fid)
            if src is None:
                continue
            key = (src.get("url"), src.get("title"), src.get("date"))
            if key in seen:
                continue
            seen.add(key)
            fuentes.append(
                {"fact_id": fid, "titulo": src.get("title"), "url": src.get("url"), "fecha": src.get("date")}
            )
        item["fuentes"] = fuentes
    return payload
