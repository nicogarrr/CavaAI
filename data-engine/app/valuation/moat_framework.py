"""Moat evidence framework — structured qualitative competitive analysis."""

from __future__ import annotations

from dataclasses import dataclass, field


MOAT_CATEGORIES = (
    "network_effects",
    "switching_costs",
    "scale_economies",
    "intangible_assets",
    "cost_advantage",
    "regulatory_barriers",
    "data_advantage",
    "distribution",
    "capital_intensity_barrier",
    "ecosystem_lock_in",
)


@dataclass
class MoatEvidence:
    type: str
    strength: float  # 0-1
    trend: str  # strengthening | stable | eroding | unknown
    evidence_for: list[str] = field(default_factory=list)
    evidence_against: list[str] = field(default_factory=list)
    persistence_years: float | None = None
    confidence: float = 0.0
    status: str = "requires_sourced_evidence"


def empty_moat_framework(company_type: str, factor_tags: list[str], special_risks: list[str]) -> dict:
    """Return a structured moat scaffold without fabricating qualitative claims."""
    suggested: list[MoatEvidence] = []

    tags = set(factor_tags)
    if "software" in tags or "platform" in tags:
        suggested.append(
            MoatEvidence(
                type="switching_costs",
                strength=0.0,
                trend="unknown",
                evidence_for=[],
                evidence_against=[],
                confidence=0.0,
            )
        )
        suggested.append(
            MoatEvidence(
                type="data_advantage",
                strength=0.0,
                trend="unknown",
                evidence_for=[],
                evidence_against=[],
                confidence=0.0,
            )
        )
    if "space" in tags or "telecom" in tags:
        suggested.append(
            MoatEvidence(
                type="regulatory_barriers",
                strength=0.0,
                trend="unknown",
                evidence_for=["spectrum / licensing — requires primary source"],
                evidence_against=["Starlink / LEO competition — requires sourced comparison"],
                confidence=0.0,
            )
        )
        suggested.append(
            MoatEvidence(
                type="capital_intensity_barrier",
                strength=0.0,
                trend="unknown",
                evidence_for=["constellation / launch capex barrier — requires sourced capex plan"],
                evidence_against=["technology commoditization risk"],
                confidence=0.0,
            )
        )
    if "quality" in tags:
        suggested.append(
            MoatEvidence(
                type="intangible_assets",
                strength=0.0,
                trend="unknown",
                evidence_for=[],
                evidence_against=[],
                confidence=0.0,
            )
        )
    if "commodities" in tags:
        suggested.append(
            MoatEvidence(
                type="cost_advantage",
                strength=0.0,
                trend="unknown",
                evidence_for=[],
                evidence_against=["commodity price taker — limited pricing power"],
                confidence=0.0,
            )
        )

    if not suggested:
        suggested = [
            MoatEvidence(type=category, strength=0.0, trend="unknown", confidence=0.0)
            for category in MOAT_CATEGORIES[:3]
        ]

    return {
        "company_type": company_type,
        "status": "scaffold_only",
        "note": (
            "Moat scores are intentionally zero until sourced evidence is attached. "
            "Do not treat this scaffold as a completed competitive analysis."
        ),
        "special_risks": special_risks,
        "moats": [
            {
                "type": m.type,
                "strength": m.strength,
                "trend": m.trend,
                "evidence_for": m.evidence_for,
                "evidence_against": m.evidence_against,
                "persistence_years": m.persistence_years,
                "confidence": m.confidence,
                "status": m.status,
            }
            for m in suggested
        ],
    }
