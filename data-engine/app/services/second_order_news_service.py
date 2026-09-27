"""On-demand, non-persistent hypotheses about indirect effects of a news item.

No signal from this service verifies a source claim or changes investment state.
The generative path is operator-gated because the provider's marginal cost has
not been established. No background job calls it during news ingestion.
"""

from __future__ import annotations

import os
import re
import unicodedata
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm import LLMRequest, Message, ResponseFormat, create_llm_provider, parse_json_response
from app.models import Company, NewsEvent
from app.services.async_bridge import run_from_any_context


class CausalStep(BaseModel):
    cause: str = Field(max_length=180)
    effect: str = Field(max_length=180)


class Theme(BaseModel):
    exposure: str = Field(max_length=100)
    direction: Literal["beneficiada", "perjudicada", "incierta"]
    chain: list[CausalStep] = Field(max_length=4)


class Extraction(BaseModel):
    themes: list[Theme] = Field(max_length=8)


# A deliberately small, public vocabulary. The fallback does not invent
# exposure or extrapolate sector labels from arbitrary narrative text.
# Keyword matches are NOT evidence that the claim in the article is true.
DETERMINISTIC_THEMES: tuple[tuple[tuple[str, ...], str, str, str], ...] = (
    (("electrification", "electrificación", "electric trucks", "camiones eléctricos"),
     "Electric Utilities", "beneficiada", "Posible aumento de demanda eléctrica"),
    (("electrification", "electrificación", "electric trucks", "camiones eléctricos"),
     "Electrical Equipment", "beneficiada", "Posible inversión en equipamiento de red"),
    (("electrification", "electrificación", "electric trucks", "camiones eléctricos"),
     "Copper", "beneficiada", "Posible demanda de materiales para infraestructura"),
    (("electrification", "electrificación", "electric trucks", "camiones eléctricos"),
     "Oil & Gas", "perjudicada", "Posible sustitución de combustible de transporte"),
)


def _normalized(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _match_keyword(text: str, term: str) -> bool:
    return f" {_normalized(term)} " in f" {_normalized(text)} "


def _fallback(text: str) -> Extraction:
    themes = []
    for terms, exposure, direction, effect in DETERMINISTIC_THEMES:
        matched = next((term for term in terms if _match_keyword(text, term)), None)
        if matched:
            themes.append(Theme(
                exposure=exposure, direction=direction,
                chain=[CausalStep(cause=f"La fuente menciona {matched}", effect=effect)],
            ))
    return Extraction(themes=themes)


_SCHEMA = Extraction.model_json_schema()


async def _extract_with_llm(text: str) -> Extraction:
    provider = create_llm_provider()
    if provider.name == "disabled":
        raise RuntimeError("LLM not configured")
    response = await provider.complete(LLMRequest(
        messages=[
            Message("system", (
                "Extrae hasta 8 hipótesis causales indirectas de la noticia. "
                "No verifiques hechos, no afirmes que la noticia es cierta. "
                "Cada exposure debe ser un nombre de sector, industria o factor "
                "que pueda coincidir literalmente con los metadatos de empresas. "
                "Devuelve una cadena explícita de 1 a 4 pasos por hipótesis. "
                "No propongas tickers; no hagas recomendaciones de inversión. "
                "Si no hay señal, devuelve themes vacío. Responde solo JSON."
            )),
            Message("user", text[:3500]),
        ],
        task="news_second_order",
        temperature=0,
        max_tokens=900,
        response_format=ResponseFormat.json_schema(_SCHEMA, name="second_order_themes"),
    ))
    return Extraction.model_validate(parse_json_response(response.text))


def _company_exposures(company: Company) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    for field in ("sector", "industry"):
        value = getattr(company, field, None)
        if isinstance(value, str) and _normalized(value) not in {"", "unknown", "other", "unassigned"}:
            values.append((field, value))
    for value in company.factor_tags or []:
        if isinstance(value, str) and _normalized(value):
            values.append(("factor_tags", value))
    return values


def _source_date(event: NewsEvent) -> str | None:
    if (event.metadata_ or {}).get("date_source") != "source":
        return None
    date = event.date
    return date.replace(tzinfo=UTC).isoformat() if date.tzinfo is None else date.isoformat()


def _jev_marker(theme: Theme) -> dict:
    """Metadata only. No TypeSafe call until the credit-aware #560 is present."""
    if os.getenv("SECOND_ORDER_JEV_ENABLED") != "1":
        return {"direction": None, "confidence": None, "backend": None}
    try:
        from app.services.jev_availability import credit_status
        from app.services.jev_gates import jev_choice_sync

        # The gate itself handles exhausted credit and operational failures.
        # A read-only availability check prevents calling an older ungated Jev.
        state = credit_status()["status"]
        if state != "activo":
            return {"direction": None, "confidence": None, "backend": None}
        decision = jev_choice_sync(
            name="second_order_direction",
            text="; ".join(f"{step.cause} -> {step.effect}" for step in theme.chain),
            instructions="Label the hypothetical direction for the exposed industry; do not verify facts.",
            criteria={"beneficiada": "could benefit", "perjudicada": "could be harmed",
                      "incierta": "direction unclear"},
        )
        if decision and decision.label in {"beneficiada", "perjudicada", "incierta"}:
            return {"direction": decision.label, "confidence": decision.confidence,
                    "backend": getattr(decision, "backend", "jev")}
    except Exception:  # noqa: BLE001 - all marker failures are best effort
        pass
    return {"direction": None, "confidence": None, "backend": None}


def _candidate(company: Company, theme: Theme, field: str, value: str,
               event: NewsEvent, marker: dict) -> dict:
    source = {"news_event_id": event.id, "url": event.url, "published_at": _source_date(event)}
    return {
        "ticker": company.ticker, "company_name": company.name,
        "direction": theme.direction, "confidence": marker["confidence"],
        "jev_direction": marker["direction"],
        "jev_backend": marker["backend"], "status": "hipótesis_no_verificada",
        "exposure": {"field": field, "value": value},
        "causal_chain": [step.model_dump() for step in theme.chain],
        "sources": [source],
        "limitations": [
            "La noticia y sus cifras son claims de la fuente, no hechos verificados.",
            "La exposición viene de metadatos del universo; no acredita ingresos ni sensibilidad económica.",
        ],
    }


def analyze_second_order(db: Session, event: NewsEvent, *, use_llm: bool = False) -> dict:
    """Read only: no commit, no thesis/score/alert changes and no ingestion filtering."""
    text = " ".join(part for part in (event.title, event.summary) if part)[:3500]
    mode = "determinista"
    llm_note = None
    extraction = _fallback(text)
    if use_llm:
        if os.getenv("SECOND_ORDER_LLM_ENABLED") != "1":
            llm_note = "LLM desactivado: coste del proveedor no verificado."
        else:
            try:
                extraction = run_from_any_context(_extract_with_llm(text))
                mode = "llm"
            except Exception:  # noqa: BLE001 - do not interrupt the read path
                llm_note = "LLM no disponible; se usa el camino determinista."
    # The LLM does not select companies. Only exact, normalized matches in
    # existing sector/industry/factor metadata can create a candidate.
    companies = db.scalars(select(Company).order_by(Company.ticker)).all()
    candidates = []
    for theme in extraction.themes:
        if not theme.chain or not _normalized(theme.exposure):
            continue
        matches = []
        for company in companies:
            for field, value in _company_exposures(company):
                if _normalized(value) == _normalized(theme.exposure):
                    matches.append((company, field, value))
                    break
            if len(matches) + len(candidates) >= 100:
                break
        if matches:
            marker = _jev_marker(theme)
            candidates.extend(
                _candidate(company, theme, field, value, event, marker)
                for company, field, value in matches
            )
        if len(candidates) >= 100:
            break
    return {
        "news_event_id": event.id, "status": "hipótesis_no_verificadas" if candidates else "sin_datos",
        "generated_at": datetime.now(UTC).isoformat(), "mode": mode,
        "source": {"url": event.url, "published_at": _source_date(event), "name": event.source},
        "source_claim": text, "source_verified": False,
        "themes": [theme.model_dump() for theme in extraction.themes],
        "candidates": candidates, "limited_to": 100, "note": llm_note,
        "warning": "Solo hipótesis. Verificar fuente, cadena causal y exposición antes de usar como conclusión.",
    }
