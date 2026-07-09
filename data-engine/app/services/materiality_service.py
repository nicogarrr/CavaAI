from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, Position
from app.services.llm_router import route_model
from app.services.source_hierarchy_service import SourceTier, classify_source


MATERIAL_KEYWORDS = {
    "dilution": ["offering", "dilution", "atm", "capital raise", "convertible", "shares"],
    "earnings": ["earnings", "guidance", "revenue", "eps", "fcf", "margin"],
    "regulatory": ["fda", "sec", "fcc", "ema", "regulatory", "investigation", "approval"],
    "contract": ["contract", "award", "customer", "backlog", "launch", "partnership"],
    "capital_allocation": ["buyback", "repurchase", "dividend", "spin-off", "asset sale"],
}

ASSUMPTIONS_BY_EVENT_TYPE = {
    "dilution": ["share_count", "cash_runway", "dilution_risk"],
    "earnings": ["revenue_growth", "fcf_margin", "guidance"],
    "regulatory": ["approval_probability", "regulatory_risk"],
    "contract": ["revenue_timing", "backlog_conversion"],
    "capital_allocation": ["share_count", "capital_allocation"],
}

POSITIVE_TERMS = ["beat", "approval", "award", "buyback", "raise", "record", "accelerate"]
NEGATIVE_TERMS = ["miss", "cut", "delay", "offering", "investigation", "default", "halt", "fraud"]
CRITICAL_TERMS = ["bankruptcy", "fraud", "halt", "default"]


@dataclass(frozen=True)
class MaterialityAssessment:
    event_type: str
    matched_event_types: list[str]
    materiality_score: int
    impact_direction: str
    affected_assumptions: list[str]
    requires_update: bool
    portfolio_weight: float
    source_tier: str
    source_trust_score: float
    reasons: list[str]
    model_route: str
    source_policy: str


class MaterialityService:
    def assess_news(
        self,
        db: Session,
        company: Company | None,
        text: str,
        source: str,
        url: str | None,
    ) -> MaterialityAssessment:
        lower_text = text.lower()
        matched_types = [
            event_type
            for event_type, keywords in MATERIAL_KEYWORDS.items()
            if any(keyword in lower_text for keyword in keywords)
        ]
        event_type = matched_types[0] if matched_types else "general_news"
        source_tier = classify_source(source, url)
        portfolio_weight = self.portfolio_weight(db, company) if company else 0.0

        materiality = 3
        reasons = ["base_score=3"]

        if matched_types:
            keyword_points = 2 * len(matched_types)
            materiality += keyword_points
            reasons.append(f"matched_event_types={','.join(matched_types)} +{keyword_points}")
        if "dilution" in matched_types:
            materiality += 2
            reasons.append("dilution +2")
        if any(word in lower_text for word in CRITICAL_TERMS):
            materiality = max(materiality, 10)
            reasons.append("critical_term => 10")
        if company and ("pre_fcf" in company.factor_tags or "speculative" in company.factor_tags):
            materiality += 1
            reasons.append("speculative/pre_fcf company +1")
        source_adjustment = self._source_adjustment(source_tier)
        if source_adjustment:
            materiality += source_adjustment
            reasons.append(f"{source_tier.key} {source_adjustment:+d}")
        portfolio_adjustment = self._portfolio_adjustment(portfolio_weight)
        if portfolio_adjustment:
            materiality += portfolio_adjustment
            reasons.append(f"portfolio_weight={portfolio_weight:.4f} {portfolio_adjustment:+d}")

        impact_direction = self._impact_direction(lower_text)
        if impact_direction == "negative" and portfolio_weight >= 0.05:
            materiality += 1
            reasons.append("negative event on meaningful position +1")

        materiality = max(1, min(materiality, 10))
        requires_update = materiality >= 7 or (portfolio_weight >= 0.10 and materiality >= 6)
        model_route = route_model(
            "deep_thesis" if requires_update else "news_triage",
            materiality_score=materiality,
            portfolio_weight=portfolio_weight,
        ).task

        return MaterialityAssessment(
            event_type=event_type,
            matched_event_types=matched_types,
            materiality_score=materiality,
            impact_direction=impact_direction,
            affected_assumptions=self._affected_assumptions(matched_types),
            requires_update=requires_update,
            portfolio_weight=portfolio_weight,
            source_tier=source_tier.key,
            source_trust_score=source_tier.trust_score,
            reasons=reasons,
            model_route=model_route,
            source_policy=source_tier.policy,
        )

    def portfolio_weight(self, db: Session, company: Company | None) -> float:
        if company is None:
            return 0.0
        positions = list(db.scalars(select(Position)).all())
        total_equity = sum(Decimal(position.market_value) for position in positions)
        if total_equity <= 0:
            return 0.0
        company_value = sum(
            Decimal(position.market_value)
            for position in positions
            if position.company_id == company.id
        )
        return float(company_value / total_equity)

    def _affected_assumptions(self, matched_types: list[str]) -> list[str]:
        assumptions: list[str] = []
        for event_type in matched_types:
            assumptions.extend(ASSUMPTIONS_BY_EVENT_TYPE.get(event_type, []))
        return sorted(set(assumptions))

    def _impact_direction(self, lower_text: str) -> str:
        if any(word in lower_text for word in POSITIVE_TERMS):
            return "positive"
        if any(word in lower_text for word in NEGATIVE_TERMS):
            return "negative"
        return "neutral"

    def _source_adjustment(self, source_tier: SourceTier) -> int:
        if source_tier.key in {"tier_1_regulatory", "tier_2_company"}:
            return 1
        if source_tier.key in {"tier_6_bootstrap", "tier_unknown"}:
            return -1
        return 0

    def _portfolio_adjustment(self, portfolio_weight: float) -> int:
        if portfolio_weight >= 0.15:
            return 2
        if portfolio_weight >= 0.05:
            return 1
        return 0
