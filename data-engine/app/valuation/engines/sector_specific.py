"""Dedicated fact-driven valuation engines for financials and REITs."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import desc, select

from app.models import FinancialFact
from app.valuation.engines.base import (
    MODEL_VERSION,
    ValuationContext,
    ValuationEngine,
    insufficient_result,
    margin_of_safety,
)
from app.valuation.moat_framework import empty_moat_framework


@dataclass(frozen=True)
class SourcedValue:
    value: float
    fact_id: int
    period: str
    confidence: float


def _latest(context: ValuationContext, *metrics: str) -> SourcedValue | None:
    fact = context.db.scalar(
        select(FinancialFact)
        .where(
            FinancialFact.company_id == context.company.id,
            FinancialFact.metric.in_(metrics),
        )
        .order_by(FinancialFact.fiscal_year.desc().nullslast(), desc(FinancialFact.created_at))
        .limit(1)
    )
    if fact is None:
        return None
    return SourcedValue(float(fact.value), fact.id, fact.period, float(fact.confidence))


def _probabilities(values: list[SourcedValue], directional_quality: float = 0.0) -> dict[str, float]:
    confidence = sum(value.confidence for value in values) / len(values)
    base = max(0.40, min(0.64, 0.38 + confidence * 0.26))
    upside_share = max(0.35, min(0.65, 0.50 + directional_quality * 0.25))
    tail = 1.0 - base
    bull = tail * upside_share
    return {"bear": tail - bull, "base": base, "bull": bull}


def _result(
    context: ValuationContext,
    *,
    engine_key: str,
    scenario_values: dict[str, float],
    probabilities: dict[str, float],
    fact_ids: dict[str, int],
    periods: dict[str, str],
    assumptions: dict,
) -> dict:
    expected = sum(scenario_values[name] * probabilities[name] for name in scenario_values)
    company = context.company
    return {
        "ticker": company.ticker,
        "model_type": company.valuation_model,
        "status": "ok",
        "publishable": True,
        "current_price": context.current_price,
        "bear_value": scenario_values["bear"],
        "base_value": scenario_values["base"],
        "bull_value": scenario_values["bull"],
        "expected_value": expected,
        "margin_of_safety": margin_of_safety(expected, context.current_price),
        "missing_inputs": [],
        "reverse_dcf": {},
        "sensitivity": {"rows": []},
        "moat": empty_moat_framework(
            company.company_type,
            company.factor_tags or [],
            company.special_risks or [],
        ),
        "trace": {
            "method": company.valuation_model,
            "engine": engine_key,
            "input_source": "financial_facts",
            "publishable": True,
            "status": "ok",
            "model_version": MODEL_VERSION,
            "scenario_style": f"{engine_key}_causal",
            "fact_ids": fact_ids,
            "periods": periods,
            "assumptions": assumptions,
            "probabilities": probabilities,
            "probability_method": "source_confidence_plus_company_quality",
        },
    }


class BankValuationEngine(ValuationEngine):
    key = "bank"

    def value(self, context: ValuationContext) -> dict:
        tangible_book = _latest(context, "tangible_book_value", "tangible_common_equity")
        shares = _latest(context, "shares_diluted")
        roe = _latest(context, "return_on_tangible_equity", "roe")
        cost_equity = _latest(context, "cost_of_equity")
        sourced = {
            "tangible_book_value": tangible_book,
            "shares_diluted": shares,
            "roe": roe,
            "cost_of_equity": cost_equity,
        }
        missing = [key for key, value in sourced.items() if value is None]
        if missing:
            return insufficient_result(
                ticker=context.company.ticker,
                model_type=context.company.valuation_model,
                engine_key=self.key,
                current_price=context.current_price,
                missing_inputs=missing,
                reason="Bank valuation requires sourced tangible book, diluted shares, ROTE/ROE and cost of equity.",
                snapshot=context.snapshot,
            )
        assert tangible_book and shares and roe and cost_equity
        growth = _latest(context, "book_value_growth", "tangible_book_growth")
        growth_value = growth.value if growth else 0.0
        if cost_equity.value <= growth_value or shares.value <= 0:
            return insufficient_result(
                ticker=context.company.ticker,
                model_type=context.company.valuation_model,
                engine_key=self.key,
                current_price=context.current_price,
                missing_inputs=["cost_of_equity_above_book_value_growth"],
                reason="A justified price-to-book model requires cost of equity above sustainable growth.",
                snapshot=context.snapshot,
            )
        book_per_share = tangible_book.value / shares.value
        specs = {
            "bear": (roe.value - 0.03, cost_equity.value + 0.015, growth_value - 0.01),
            "base": (roe.value, cost_equity.value, growth_value),
            "bull": (roe.value + 0.025, max(cost_equity.value - 0.01, growth_value + 0.005), growth_value + 0.005),
        }
        values = {
            name: book_per_share * max(0.25, min(3.0, (scenario_roe - scenario_growth) / (scenario_cost - scenario_growth)))
            for name, (scenario_roe, scenario_cost, scenario_growth) in specs.items()
        }
        available = [value for value in sourced.values() if value is not None] + ([growth] if growth else [])
        probabilities = _probabilities(available, roe.value - cost_equity.value)
        return _result(
            context,
            engine_key=self.key,
            scenario_values=values,
            probabilities=probabilities,
            fact_ids={key: value.fact_id for key, value in sourced.items() if value},
            periods={key: value.period for key, value in sourced.items() if value},
            assumptions={"book_per_share": book_per_share, "scenario_roe_cost_growth": specs},
        )


class InsurerValuationEngine(ValuationEngine):
    key = "insurer"

    def value(self, context: ValuationContext) -> dict:
        book = _latest(context, "book_value", "common_equity")
        shares = _latest(context, "shares_diluted")
        roe = _latest(context, "roe")
        cost_equity = _latest(context, "cost_of_equity")
        combined_ratio = _latest(context, "combined_ratio")
        sourced = {
            "book_value": book,
            "shares_diluted": shares,
            "roe": roe,
            "cost_of_equity": cost_equity,
            "combined_ratio": combined_ratio,
        }
        missing = [key for key, value in sourced.items() if value is None]
        if missing:
            return insufficient_result(
                ticker=context.company.ticker,
                model_type=context.company.valuation_model,
                engine_key=self.key,
                current_price=context.current_price,
                missing_inputs=missing,
                reason="Insurer valuation requires sourced book value, shares, ROE, cost of equity and combined ratio.",
                snapshot=context.snapshot,
            )
        assert book and shares and roe and cost_equity and combined_ratio
        growth = _latest(context, "book_value_growth")
        growth_value = growth.value if growth else 0.0
        if shares.value <= 0 or cost_equity.value <= growth_value:
            return insufficient_result(
                ticker=context.company.ticker,
                model_type=context.company.valuation_model,
                engine_key=self.key,
                current_price=context.current_price,
                missing_inputs=["valid_shares_and_cost_of_equity_spread"],
                reason="Insurer price-to-book model inputs are economically inconsistent.",
                snapshot=context.snapshot,
            )
        book_per_share = book.value / shares.value
        specs = {
            "bear": (roe.value - 0.025, cost_equity.value + 0.015, combined_ratio.value + 0.03),
            "base": (roe.value, cost_equity.value, combined_ratio.value),
            "bull": (roe.value + 0.02, max(cost_equity.value - 0.01, growth_value + 0.005), combined_ratio.value - 0.025),
        }
        values = {}
        for name, (scenario_roe, scenario_cost, scenario_combined) in specs.items():
            justified_pb = (scenario_roe - growth_value) / (scenario_cost - growth_value)
            underwriting_quality = max(0.75, min(1.25, 1 + (1 - scenario_combined) * 2))
            values[name] = book_per_share * max(0.25, min(3.0, justified_pb)) * underwriting_quality
        probabilities = _probabilities(list(sourced.values()), 1 - combined_ratio.value)
        return _result(
            context,
            engine_key=self.key,
            scenario_values=values,
            probabilities=probabilities,
            fact_ids={key: value.fact_id for key, value in sourced.items() if value},
            periods={key: value.period for key, value in sourced.items() if value},
            assumptions={"book_per_share": book_per_share, "scenario_roe_cost_combined_ratio": specs},
        )


class ReitValuationEngine(ValuationEngine):
    key = "reit"

    def value(self, context: ValuationContext) -> dict:
        noi = _latest(context, "net_operating_income", "noi")
        cap_rate = _latest(context, "capitalization_rate", "cap_rate")
        net_debt = _latest(context, "net_debt")
        shares = _latest(context, "shares_diluted")
        sourced = {
            "net_operating_income": noi,
            "cap_rate": cap_rate,
            "net_debt": net_debt,
            "shares_diluted": shares,
        }
        missing = [key for key, value in sourced.items() if value is None]
        if missing:
            return insufficient_result(
                ticker=context.company.ticker,
                model_type=context.company.valuation_model,
                engine_key=self.key,
                current_price=context.current_price,
                missing_inputs=missing,
                reason="REIT NAV requires sourced NOI, cap rate, net debt and diluted shares.",
                snapshot=context.snapshot,
            )
        assert noi and cap_rate and net_debt and shares
        if cap_rate.value <= 0 or shares.value <= 0:
            return insufficient_result(
                ticker=context.company.ticker,
                model_type=context.company.valuation_model,
                engine_key=self.key,
                current_price=context.current_price,
                missing_inputs=["positive_cap_rate_and_shares"],
                reason="REIT NAV inputs must be positive.",
                snapshot=context.snapshot,
            )
        specs = {
            "bear": (noi.value * 0.94, cap_rate.value + 0.0075),
            "base": (noi.value, cap_rate.value),
            "bull": (noi.value * 1.06, max(cap_rate.value - 0.005, 0.001)),
        }
        values = {
            name: max(0.0, scenario_noi / scenario_cap_rate - net_debt.value) / shares.value
            for name, (scenario_noi, scenario_cap_rate) in specs.items()
        }
        probabilities = _probabilities(list(sourced.values()), -cap_rate.value)
        return _result(
            context,
            engine_key=self.key,
            scenario_values=values,
            probabilities=probabilities,
            fact_ids={key: value.fact_id for key, value in sourced.items() if value},
            periods={key: value.period for key, value in sourced.items() if value},
            assumptions={"scenario_noi_cap_rate": specs, "net_debt": net_debt.value},
        )
