"""Valuation engine contracts and shared helpers."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import CalculatedMetric, Company
from app.valuation.financial_snapshot import FinancialSnapshot, FinancialSnapshotBuilder
from app.valuation.moat_framework import empty_moat_framework


# v2: net_debt is a required DCF input (no longer coerced to zero debt), the
# FCF-margin clamp no longer flips the sign of a known-negative margin, the
# traceable WACC is preferred over the tag default, and the reverse DCF
# withholds its value when the price is out of bounds. Snapshots persisted
# under v1 were computed with a fabricated net_debt and are not comparable.
MODEL_VERSION = "valuation-engines-v2"


def traceable_wacc(db: Session, company: Company) -> float | None:
    """Return the persisted, traceable WACC for this company, if any.

    ``metric_calculation_service`` / ``WaccInputService`` already compute a
    dated, sourced WACC (risk-free + ERP + beta + capital-structure weights).
    The valuation engines must prefer it over the tag-based policy default so
    the same company is not discounted at 10% and 6.2% depending on which
    module answers.
    """
    metric = db.scalar(
        select(CalculatedMetric)
        .where(
            CalculatedMetric.company_id == company.id,
            CalculatedMetric.metric == "wacc",
            CalculatedMetric.status == "ok",
            CalculatedMetric.value.is_not(None),
        )
        .order_by(
            CalculatedMetric.fiscal_year.desc().nullslast(),
            desc(CalculatedMetric.created_at),
        )
        .limit(1)
    )
    if metric is None or metric.value is None:
        return None
    value = float(metric.value)
    if not math.isfinite(value) or not 0.0 < value < 1.0:
        return None
    return value


def clamp_fcf_margin(margin: float, *, ceiling: float) -> tuple[float, bool]:
    """Clamp a known FCF margin without ever flipping its sign.

    A negative FCF margin is a *known fact* (the company burns cash), not a
    degenerate input, so it is preserved. Only the ceiling is applied.
    """
    clamped = min(margin, ceiling)
    return clamped, clamped != margin


@dataclass
class ValuationContext:
    db: Session
    company: Company
    snapshot: FinancialSnapshot
    current_price: float | None
    engine_key: str


def insufficient_result(
    *,
    ticker: str,
    model_type: str,
    engine_key: str,
    current_price: float | None,
    missing_inputs: list[str],
    reason: str,
    snapshot: FinancialSnapshot | None = None,
    extra_trace: dict | None = None,
) -> dict:
    trace: dict[str, Any] = {
        "method": model_type,
        "engine": engine_key,
        "input_source": "insufficient_data",
        "publishable": False,
        "status": "insufficient_data",
        "missing_inputs": missing_inputs,
        "reason": reason,
        "model_version": MODEL_VERSION,
        "fact_ids": snapshot.fact_ids() if snapshot else {},
        "periods": snapshot.periods() if snapshot else {},
        "snapshot": {
            "as_of": snapshot.as_of_period if snapshot else None,
            "income_statement": snapshot.income_statement if snapshot else None,
            "balance_sheet": snapshot.balance_sheet if snapshot else None,
            "shares": snapshot.shares_period if snapshot else None,
            "warnings": snapshot.warnings if snapshot else [],
        },
    }
    if extra_trace:
        trace.update(extra_trace)

    return {
        "ticker": ticker,
        "model_type": model_type,
        "status": "insufficient_data",
        "publishable": False,
        "current_price": current_price,
        "bear_value": None,
        "base_value": None,
        "bull_value": None,
        "expected_value": None,
        "margin_of_safety": None,
        "missing_inputs": missing_inputs,
        "reverse_dcf": {},
        "sensitivity": {"rows": []},
        "trace": trace,
        "moat": empty_moat_framework(
            # company fields filled by caller via extra if needed
            "",
            [],
            [],
        ),
    }


class ValuationEngine(ABC):
    key: str = "base"

    @abstractmethod
    def value(self, context: ValuationContext) -> dict:
        raise NotImplementedError

    def build_context(
        self,
        db: Session,
        company: Company,
        current_price: float | None,
    ) -> ValuationContext:
        snapshot = FinancialSnapshotBuilder().build(db, company)
        return ValuationContext(
            db=db,
            company=company,
            snapshot=snapshot,
            current_price=current_price,
            engine_key=self.key,
        )


def default_growth(company: Company) -> float:
    """Crecimiento de ingresos por defecto cuando el snapshot no trae ``revenue_growth``.

    Supuesto por tags: pre-FCF/speculative 20%, software/IA 10%,
    commodities 4%, resto 7%. El motor lo acota a [-15%, +45%]
    (+60% en pre-revenue).
    """
    tags = company.factor_tags or []
    if "pre_fcf" in tags or "speculative" in tags:
        return 0.20
    if "software" in tags or "ai" in tags:
        return 0.10
    if "commodities" in tags:
        return 0.04
    return 0.07


def default_wacc(company: Company) -> float:
    """WACC por defecto (fuente ``tag_default`` en el trace).

    Supuesto por tags: pre-FCF/speculative 13%, commodities/china 11%,
    quality 8.5%, resto 10%. El DCF exige ``WACC > crecimiento terminal``;
    los escenarios lo mueven +2pp (bear) / −1pp (bull, con suelo).
    """
    tags = company.factor_tags or []
    if "pre_fcf" in tags or "speculative" in tags:
        return 0.13
    if "commodities" in tags or "china" in tags:
        return 0.11
    if "quality" in tags:
        return 0.085
    return 0.10


def default_terminal_growth(company: Company) -> float:
    """Crecimiento terminal por defecto (Gordon en el valor terminal).

    Supuesto por tags: commodities 1.5%, pre-FCF/speculative 2.5%,
    resto 3%. Fijo en los tres escenarios; el DCF lo valida con
    ``WACC > terminal``.
    """
    tags = company.factor_tags or []
    if "commodities" in tags:
        return 0.015
    if "pre_fcf" in tags or "speculative" in tags:
        return 0.025
    return 0.03


def margin_of_safety(expected_value: float | None, current_price: float | None) -> float | None:
    if expected_value is None or current_price is None or current_price <= 0:
        return None
    return expected_value / current_price - 1
