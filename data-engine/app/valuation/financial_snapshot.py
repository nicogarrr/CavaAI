"""Build a temporally coherent financial snapshot for valuation inputs.

Independent per-metric "latest" queries can mix FY revenue with TTM FCF and
stale shares. This builder anchors on a primary income-statement period and
only accepts companion facts from the same economic snapshot (or a compatible
balance-sheet instant).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import Company, FinancialFact

DURATION_METRICS = ("revenue", "free_cash_flow", "fcf_margin", "revenue_growth")
INSTANT_METRICS = (
    "net_debt",
    "shares_diluted",
    "cash_and_equivalents",
    "total_debt",
    "operating_cash_flow",
    "capital_expenditure",
)
REQUIRED_FOR_DCF = ("revenue", "shares_diluted")


@dataclass
class FinancialSnapshot:
    as_of_period: str | None = None
    fiscal_year: int | None = None
    fiscal_quarter: str | None = None
    period_type: str | None = None  # FY | Q | TTM
    income_statement: str | None = None
    balance_sheet: str | None = None
    shares_period: str | None = None
    facts: dict[str, FinancialFact] = field(default_factory=dict)
    missing_inputs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    coherent: bool = False

    def value(self, metric: str) -> float | None:
        fact = self.facts.get(metric)
        return float(fact.value) if fact is not None else None

    def fact_ids(self) -> dict[str, int | None]:
        return {metric: fact.id for metric, fact in self.facts.items()}

    def periods(self) -> dict[str, str | None]:
        return {metric: fact.period for metric, fact in self.facts.items()}


def _period_type(period: str | None, fiscal_quarter: str | None) -> str:
    text = (period or "").upper()
    if "TTM" in text:
        return "TTM"
    if fiscal_quarter and fiscal_quarter.upper() not in {"FY", "ANNUAL", ""}:
        return "Q"
    if text.startswith("Q") or "Q1" in text or "Q2" in text or "Q3" in text or "Q4" in text:
        return "Q"
    return "FY"


def _facts_for_metric(db: Session, company_id: int, metric: str) -> list[FinancialFact]:
    return list(
        db.scalars(
            select(FinancialFact)
            .where(FinancialFact.company_id == company_id, FinancialFact.metric == metric)
            .order_by(
                FinancialFact.fiscal_year.desc().nullslast(),
                desc(FinancialFact.created_at),
            )
        ).all()
    )


def _same_duration_period(anchor: FinancialFact, candidate: FinancialFact) -> bool:
    if anchor.fiscal_year is not None and candidate.fiscal_year is not None:
        if candidate.fiscal_year != anchor.fiscal_year:
            return False
        anchor_q = (anchor.fiscal_quarter or "FY").upper()
        cand_q = (candidate.fiscal_quarter or "FY").upper()
        if anchor_q in {"FY", "ANNUAL"} and cand_q in {"FY", "ANNUAL", ""}:
            return True
        return anchor_q == cand_q
    return (anchor.period or "").upper() == (candidate.period or "").upper()


def _compatible_instant(anchor: FinancialFact, candidate: FinancialFact) -> bool:
    """Balance-sheet / shares may be same FY or a later instant in the same year."""
    if anchor.fiscal_year is None or candidate.fiscal_year is None:
        return (anchor.period or "").upper() == (candidate.period or "").upper()
    if candidate.fiscal_year < anchor.fiscal_year:
        return False
    if candidate.fiscal_year > anchor.fiscal_year + 1:
        return False
    return True


def _pick_matching(
    candidates: list[FinancialFact],
    anchor: FinancialFact,
    *,
    instant: bool,
) -> FinancialFact | None:
    matcher = _compatible_instant if instant else _same_duration_period
    for fact in candidates:
        if matcher(anchor, fact):
            return fact
    return None


class FinancialSnapshotBuilder:
    """Assemble a coherent valuation snapshot from FinancialFact rows."""

    def build(self, db: Session, company: Company) -> FinancialSnapshot:
        revenue_candidates = _facts_for_metric(db, company.id, "revenue")
        if not revenue_candidates:
            return FinancialSnapshot(
                missing_inputs=["revenue", "shares_diluted", "free_cash_flow_or_fcf_margin"],
                coherent=False,
            )

        anchor = revenue_candidates[0]
        snapshot = FinancialSnapshot(
            as_of_period=anchor.period,
            fiscal_year=anchor.fiscal_year,
            fiscal_quarter=anchor.fiscal_quarter,
            period_type=_period_type(anchor.period, anchor.fiscal_quarter),
            income_statement=anchor.period,
            facts={"revenue": anchor},
        )

        for metric in DURATION_METRICS:
            if metric == "revenue":
                continue
            match = _pick_matching(_facts_for_metric(db, company.id, metric), anchor, instant=False)
            if match:
                snapshot.facts[metric] = match
            else:
                latest = _facts_for_metric(db, company.id, metric)
                if latest:
                    snapshot.warnings.append(
                        f"{metric} latest period {latest[0].period} does not match "
                        f"anchor {anchor.period}; excluded from snapshot."
                    )

        for metric in INSTANT_METRICS:
            match = _pick_matching(_facts_for_metric(db, company.id, metric), anchor, instant=True)
            if match:
                snapshot.facts[metric] = match
                if metric == "net_debt":
                    snapshot.balance_sheet = match.period
                if metric == "shares_diluted":
                    snapshot.shares_period = match.period
            else:
                latest = _facts_for_metric(db, company.id, metric)
                if latest:
                    snapshot.warnings.append(
                        f"{metric} latest period {latest[0].period} is incompatible "
                        f"with anchor {anchor.period}; excluded from snapshot."
                    )

        missing: list[str] = []
        if "revenue" not in snapshot.facts or float(snapshot.facts["revenue"].value) <= 0:
            missing.append("revenue")
        if "shares_diluted" not in snapshot.facts or float(snapshot.facts["shares_diluted"].value) <= 0:
            missing.append("shares_diluted")

        has_margin = "fcf_margin" in snapshot.facts
        has_fcf = "free_cash_flow" in snapshot.facts
        if not has_margin and not has_fcf:
            missing.append("normalized_fcf_or_fcf_margin")

        snapshot.missing_inputs = missing
        snapshot.coherent = not missing
        return snapshot
