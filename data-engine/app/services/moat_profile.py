"""Conservative context for the financial quality checks, not a moat verdict.

Explicit company metadata selects a profile. Financial facts alone cannot prove
whether a company has a durable competitive advantage or is pre-revenue.
"""

from __future__ import annotations

from app.models import Company

PROFILE_LABELS = {
    "early_stage": "Etapa temprana / antes de caja recurrente",
    "financial": "Financiera",
    "cyclical": "Cíclica o materias primas",
    "growth": "Crecimiento / expansión",
    "mature": "Negocio operativo (perfil general)",
    "unknown": "Etapa no clasificada",
}


def financial_quality_profile(company: Company) -> tuple[str, str]:
    """Select a profile only from explicit, persisted company metadata."""
    kind = (company.company_type or "").lower()
    model = (company.valuation_model or "").lower()
    tags = {str(tag).lower() for tag in (company.factor_tags or [])}
    sector = (company.sector or "").lower()
    if "pre_revenue" in kind or "pre_fcf" in kind or "pre_fcf" in tags:
        return "early_stage", "Tipo/etiqueta de empresa: antes de caja recurrente; no implica ingresos nulos."
    if any(word in kind for word in ("bank", "insurer", "insurance", "asset_manager")) or sector == "financials":
        return "financial", "Sector o tipo financiero registrado."
    if "commodities" in tags or "cyclical" in tags or any(word in kind for word in ("mining", "commodity")):
        return "cyclical", "Etiqueta cíclica o de materias primas registrada."
    if "growth" in tags or "growth" in kind or "speculative" in tags or "speculative" in model:
        return "growth", "Etiqueta de crecimiento o escenario especulativo registrada."
    # Creation/import paths seed these placeholders before company enrichment.
    # A placeholder in either field cannot establish an operating profile.
    if kind in {"", "research_candidate", "unknown", "unassigned"} or model in {"", "unassigned", "unknown"}:
        return "unknown", "No consta clasificación suficiente de la empresa."
    return "mature", "Perfil operativo general; no equivale a demostrar madurez ni foso."


#: Metrics below are not a validated proxy for moat in these profiles.
#: Preserve their raw values in individual calculated metrics for diagnostics.
NONCOMPARABLE_PROFILES = frozenset({"early_stage", "financial", "cyclical", "growth", "unknown"})

#: El perfil clasifica la etapa operativa de la empresa. No es un veredicto de
#: foso: ninguna de estas etiquetas prueba ni descarta una ventaja competitiva,
#: asi que nunca debe usarse para recortar o bajar puntuaciones de evidencia.
PROFILE_IS_NOT_A_MOAT_VERDICT = (
    "El perfil describe la etapa operativa a partir de metadatos explicitos de "
    "la empresa; no demuestra ni descarta un foso competitivo."
)


def moat_evidence_context(company: Company) -> dict:
    """Contexto de perfil para acompanar a una evaluacion de foso.

    Aditivo: el perfil se expone como contexto para que el lector sepa si la
    empresa esta antes de caja, es ciclica, financiera,etc. y lo que eso exige
    como evidencia. No puntua, no filtra y no baja el score: un foso se
    demuestra con fuentes, no con la etapa operativa.
    """
    profile, reason = financial_quality_profile(company)
    return {
        "profile": profile,
        "profile_label": PROFILE_LABELS.get(profile, profile),
        "profile_reason": reason,
        "score_comparable": profile not in NONCOMPARABLE_PROFILES,
        "note": PROFILE_IS_NOT_A_MOAT_VERDICT,
    }
