"""On-demand, non-persistent hypotheses about indirect effects of a news item.

No signal from this service verifies a source claim or changes investment state.
The generative path is operator-gated and limited to the verified free model.
No background job calls it during news ingestion.
"""

from __future__ import annotations

import os
import re
import unicodedata
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.llm import LLMRequest, Message, ResponseFormat, create_llm_provider, parse_json_response
from app.models import Company, NewsEvent
from app.services.async_bridge import run_from_any_context
from app.services.second_order_quota import reserve_llm_call


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


async def _extract_with_llm(text: str) -> tuple[Extraction, object]:
    provider = create_llm_provider()
    if provider.name == "disabled":
        raise RuntimeError("LLM not configured")
    request = LLMRequest(
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
        model="space-bunny-free",
        temperature=0,
        max_tokens=900,
        response_format=ResponseFormat.json_schema(_SCHEMA, name="second_order_themes"),
    )
    # Pin the exact free model: task overrides and env defaults may route to paid models.
    if provider.model_router.resolve(request) != "space-bunny-free":
        raise RuntimeError("Second-order model is not the verified free model")
    response = await provider.complete(request)
    return Extraction.model_validate(parse_json_response(response.text)), response


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


# Accent folding replicated in SQL so the prefilter sees the same alphabet
# as _normalized (NFKD -> ascii-ignore) for the Spanish Latin-1 set, BOTH
# cases (ÁÉÍÓÚÜÑ áéíóúüñ): SQLite lower() is ASCII-only, so uppercase
# accented letters must be replaced BEFORE lower(). JSON-cast columns get two
# SEPARATE folded expressions OR-ed (real characters for Postgres JSONB;
# \uXXXX escapes for SQLite's JSON serializer) because one 28-deep replace
# chain overflows SQLite's parser stack.
# Scope declared: Spanish accented vowels + ñ, upper and lower case. Other
# Unicode simply misses the prefilter; this is NOT a general Unicode superset.
_SQL_FOLD_UPPER = (("Á", "A"), ("É", "E"), ("Í", "I"), ("Ó", "O"),
                   ("Ú", "U"), ("Ü", "U"), ("Ñ", "N"))
_SQL_FOLD_LOWER = (("á", "a"), ("é", "e"), ("í", "i"),
                   ("ó", "o"), ("ú", "u"), ("ü", "u"), ("ñ", "n"))
_SQL_FOLD_ESCAPES_UPPER = (("\\u00c1", "A"), ("\\u00c9", "E"), ("\\u00cd", "I"),
                           ("\\u00d3", "O"), ("\\u00da", "U"), ("\\u00dc", "U"),
                           ("\\u00d1", "N"))
_SQL_FOLD_ESCAPES_LOWER = (("\\u00e1", "a"), ("\\u00e9", "e"), ("\\u00ed", "i"),
                           ("\\u00f3", "o"), ("\\u00fa", "u"), ("\\u00fc", "u"),
                           ("\\u00f1", "n"))


def _fold_pairs(expr, upper, lower):
    for ch, base in upper:
        expr = func.replace(expr, ch, base)
    expr = func.lower(expr)
    for ch, base in lower:
        expr = func.replace(expr, ch, base)
    return expr


def _sql_fold(column):
    """Fold real characters: Postgres JSONB and plain text columns."""
    return _fold_pairs(column, _SQL_FOLD_UPPER, _SQL_FOLD_LOWER)


def _sql_fold_json_escapes(column):
    """Fold escaped sequences: SQLite JSON serializer output."""
    return _fold_pairs(column, _SQL_FOLD_ESCAPES_UPPER, _SQL_FOLD_ESCAPES_LOWER)


def _matching_companies(db: Session, exposure: str) -> list[Company]:
    """Prefilter in SQL, then confirm normalized metadata matches in Python.

    The prefilter is a proven superset of the Python check: Python accepts a
    company only when _normalized(field) == _normalized(exposure), and every
    [a-z0-9]+ token of the normalized exposure then appears verbatim as an
    alnum run inside the accent-folded lowercase field (normalization only
    turns punctuation into spaces; it never removes or merges alnum chars).
    Matching ANY token in ANY folded field therefore keeps every exact match.

    No LIMIT before Python validation: an early cap could drop a real match
    behind loose token hits. The result is still selective in practice (the
    alternative was loading the whole universe); the candidate cap applies
    after validation.
    """
    exposure_norm = _normalized(exposure)
    if not exposure_norm:
        return []
    token_predicates = [
        or_(
            _sql_fold(Company.sector).like(f"%{token}%"),
            _sql_fold(Company.industry).like(f"%{token}%"),
            _sql_fold(cast(Company.factor_tags, String)).like(f"%{token}%"),
            _sql_fold_json_escapes(cast(Company.factor_tags, String)).like(f"%{token}%"),
        )
        for token in exposure_norm.split()
    ]
    return list(db.scalars(
        select(Company).where(or_(*token_predicates)).order_by(Company.ticker)
    ).all())


def analyze_second_order(db: Session, event: NewsEvent, *, use_llm: bool = False) -> dict:
    """No thesis/score/alert changes or ingestion filtering; reserves LLM quota."""
    text = " ".join(part for part in (event.title, event.summary) if part)[:3500]
    mode = "determinista"
    llm_note = None
    llm_quota = None
    extraction = _fallback(text)
    if use_llm:
        if os.getenv("SECOND_ORDER_LLM_ENABLED") != "1":
            llm_note = "Análisis LLM desactivado por configuración."
        else:
            try:
                llm_quota = reserve_llm_call(db.info.get("tenant_id"), get_settings())
                if not llm_quota["allowed"]:
                    llm_note = "Análisis LLM no disponible: tope alcanzado."
                else:
                    extraction, _response = run_from_any_context(_extract_with_llm(text))
                    mode = "llm"
            except Exception:  # noqa: BLE001 - never claim a failed call worked
                llm_note = "Análisis LLM no disponible; se usa el camino determinista."
    # The LLM does not select companies. Only exact, normalized matches in
    # existing sector/industry/factor metadata can create a candidate.
    candidates = []
    for theme in extraction.themes:
        if not theme.chain or not _normalized(theme.exposure):
            continue
        matches = []
        for company in _matching_companies(db, theme.exposure):
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
        "llm_quota": llm_quota,
        "warning": "Solo hipótesis. Verificar fuente, cadena causal y exposición antes de usar como conclusión.",
    }
