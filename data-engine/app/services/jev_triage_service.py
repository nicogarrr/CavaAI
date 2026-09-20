"""Triage barato de noticias con TypeSafe Jev delante del LLM principal.

Si Jev clasifica la noticia como "routine" con confianza alta, se guardinga
la ruta del LLM principal (news_triage barato) y se abre la gate para
degradar profundidad. Nunca decide solo: solo ajusta materiality/reasoning.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core.config import get_settings

logger = logging.getLogger("cavaai.jev_triage")

# Umbral de confianza de Jev para degradar a "routine".
ROUTINE_CONFIDENCE_THRESHOLD = 0.85
# Si Jev dice "urgent" con esta confianza, sumamos materialidad.
URGENT_CONFIDENCE_THRESHOLD = 0.80
URGENT_MATERIALITY_BUMP = 1


@dataclass(frozen=True)
class JevTriageResult:
    label: str
    confidence: float
    applied: bool  # True si el resultado influyó en el score
    latency_s: float
    error: str | None = None


def build_client():
    """Devuelve JevDecisionClient o None si no hay TYPESAFE_API_KEY."""
    settings = get_settings()
    if not settings.typesafe_api_key:
        return None
    # import diferido para no penalizar arranque sin key
    from app.llm.jev import JevDecisionClient

    return JevDecisionClient(
        api_key=settings.typesafe_api_key,
        base_url=settings.typesafe_base_url,
        default_model=settings.typesafe_model,
    )


CRITERIA = {
    "urgent": (
        "price crash, circuit breaker, bankruptcy, fraud, accounting scandal, "
        "regulatory investigation, downgrade to junk, guidance cut, dilution, "
        "halted trading, urgent investor action needed"
    ),
    "routine": (
        "mild move on a quiet session, routine news, no new facts, opinion piece, "
        "conference appearance without announcements, generic market commentary"
    ),
}


def classify_urgency_sync(text: str) -> JevTriageResult | None:
    """Clasifica urgencia con Jev. Devuelve None si no está configurado o falla."""
    client = build_client()
    if client is None:
        return None
    import asyncio

    try:
        decision = asyncio.run(
            client.classify(
                text[:2000],
                name="urgency",
                instructions="How urgent is this market news for an investor?",
                criteria=CRITERIA,
            )
        )
    except Exception as exc:  # noqa: BLE001 — best-effort, nunca rompe ingesta
        logger.warning("jev triage failed: %s", exc)
        return JevTriageResult(
            label="", confidence=0.0, applied=False, latency_s=0.0,
            error=f"{type(exc).__name__}: {exc}",
        )
    return JevTriageResult(
        label=decision.label,
        confidence=decision.confidence,
        applied=False,
        latency_s=decision.latency_s,
    )


def apply_to_materiality(
    materiality: int, reasons: list[str], triage: JevTriageResult
) -> int:
    """Ajusta materialidad en sitio según el veredicto de Jev (sin romper clamps externos)."""
    if triage.label == "urgent" and triage.confidence >= URGENT_CONFIDENCE_THRESHOLD:
        materiality += URGENT_MATERIALITY_BUMP
        reasons.append(
            f"jev_urgent(conf={triage.confidence:.2f}) +{URGENT_MATERIALITY_BUMP}"
        )
    elif triage.label == "routine" and triage.confidence >= ROUTINE_CONFIDENCE_THRESHOLD:
        materiality -= 1
        reasons.append(f"jev_routine(conf={triage.confidence:.2f}) -1")
    return materiality
