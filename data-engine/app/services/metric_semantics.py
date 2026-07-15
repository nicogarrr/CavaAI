"""Meaning and tolerances used when comparing forecasts with actuals."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class MetricSemantics:
    direction: str
    tolerance: Decimal


class MetricSemanticsRegistry:
    _RULES = {
        "revenue": MetricSemantics("higher_is_better", Decimal("0.05")),
        "gross_profit": MetricSemantics("higher_is_better", Decimal("0.05")),
        "operating_income": MetricSemantics("higher_is_better", Decimal("0.075")),
        "ebitda": MetricSemantics("higher_is_better", Decimal("0.075")),
        "net_income": MetricSemantics("higher_is_better", Decimal("0.10")),
        "operating_cash_flow": MetricSemantics("higher_is_better", Decimal("0.075")),
        "free_cash_flow": MetricSemantics("higher_is_better", Decimal("0.075")),
        "fcf_margin": MetricSemantics("higher_is_better", Decimal("0.05")),
        "roic": MetricSemantics("higher_is_better", Decimal("0.05")),
        "net_debt": MetricSemantics("lower_is_better", Decimal("0.05")),
        "shares_diluted": MetricSemantics("lower_is_better", Decimal("0.02")),
        "churn": MetricSemantics("lower_is_better", Decimal("0.05")),
        "combined_ratio": MetricSemantics("lower_is_better", Decimal("0.02")),
        "working_capital_absorption": MetricSemantics("lower_is_better", Decimal("0.10")),
        "capital_expenditure": MetricSemantics("context_dependent", Decimal("0.10")),
        "working_capital": MetricSemantics("context_dependent", Decimal("0.10")),
    }

    @classmethod
    def get(cls, metric: str) -> MetricSemantics:
        return cls._RULES.get(
            metric.strip().lower(),
            MetricSemantics("context_dependent", Decimal("0.05")),
        )

    @classmethod
    def classify(
        cls, metric: str, expected: Decimal, actual: Decimal
    ) -> tuple[str, Decimal | None]:
        variance = actual - expected
        variance_percent = variance / abs(expected) if expected != 0 else None
        rule = cls.get(metric)
        if variance_percent is None or abs(variance_percent) <= rule.tolerance:
            return "met", variance_percent
        if rule.direction == "higher_is_better":
            return ("beat" if variance_percent > 0 else "miss"), variance_percent
        if rule.direction == "lower_is_better":
            return ("beat" if variance_percent < 0 else "miss"), variance_percent
        return "outside_tolerance", variance_percent
