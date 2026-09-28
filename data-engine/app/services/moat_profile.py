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
    if kind or model:
        return "mature", "Perfil operativo general; no equivale a demostrar madurez ni foso."
    return "unknown", "No consta clasificación suficiente de la empresa."


# Metrics below are not a validated proxy for moat in these profiles.
# Preserve their raw values in individual calculated metrics for diagnostics.
NONCOMPARABLE_PROFILES = frozenset({"early_stage", "financial", "cyclical", "growth", "unknown"})
