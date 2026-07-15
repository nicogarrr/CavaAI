"""Commodity-cycle engine — requires volume/cost facts; no bootstrap."""

from __future__ import annotations

from sqlalchemy import desc, select

from app.models import FinancialFact
from app.valuation.commodity_sensitivity import commodity_price_sensitivity
from app.valuation.engines.base import (
    MODEL_VERSION,
    ValuationContext,
    ValuationEngine,
    insufficient_result,
    margin_of_safety,
)
from app.valuation.moat_framework import empty_moat_framework
from app.valuation.scenario_definitions import evidence_weighted_probabilities
from app.valuation.scenario_model import Scenario, probability_weighted_value


class CommodityCycleEngine(ValuationEngine):
    key = "commodity"

    def value(self, context: ValuationContext) -> dict:
        company = context.company
        snapshot = context.snapshot
        current_price = context.current_price

        def latest(metric: str) -> FinancialFact | None:
            return context.db.scalar(
                select(FinancialFact)
                .where(FinancialFact.company_id == company.id, FinancialFact.metric == metric)
                .order_by(FinancialFact.fiscal_year.desc().nullslast(), desc(FinancialFact.created_at))
                .limit(1)
            )

        volume_fact = latest("production_volume") or latest("sales_volume")
        cost_fact = latest("cash_cost_per_unit") or latest("all_in_sustaining_cost")
        price_fact = latest("realized_commodity_price") or latest("spot_commodity_price")
        tax_fact = latest("effective_tax_rate")
        multiple_fact = latest("commodity_earnings_multiple")
        shares = snapshot.value("shares_diluted")
        net_debt = snapshot.value("net_debt") or 0.0

        missing: list[str] = []
        if volume_fact is None:
            missing.append("production_volume_or_sales_volume")
        if cost_fact is None:
            missing.append("cash_cost_per_unit")
        if price_fact is None:
            missing.append("realized_or_spot_commodity_price")
        if tax_fact is None:
            missing.append("effective_tax_rate")
        if multiple_fact is None:
            missing.append("commodity_earnings_multiple")
        if shares is None or shares <= 0:
            missing.append("shares_diluted")

        if missing:
            result = insufficient_result(
                ticker=company.ticker,
                model_type=company.valuation_model,
                engine_key=self.key,
                current_price=current_price,
                missing_inputs=missing,
                reason="Commodity valuation requires volume, unit cost, price and shares — not a generic DCF.",
                snapshot=snapshot,
            )
            result["moat"] = empty_moat_framework(
                company.company_type, company.factor_tags or [], company.special_risks or []
            )
            return result

        assert volume_fact and cost_fact and price_fact and tax_fact and multiple_fact and shares
        if not 0 <= float(tax_fact.value) < 1 or float(multiple_fact.value) <= 0:
            result = insufficient_result(
                ticker=company.ticker,
                model_type=company.valuation_model,
                engine_key=self.key,
                current_price=current_price,
                missing_inputs=["valid_effective_tax_rate_and_commodity_earnings_multiple"],
                reason="Commodity tax and valuation multiple assumptions must be sourced and economically valid.",
                snapshot=snapshot,
            )
            result["moat"] = empty_moat_framework(
                company.company_type, company.factor_tags or [], company.special_risks or []
            )
            return result

        base_price = float(price_fact.value)
        grid = commodity_price_sensitivity(
            base_volume=float(volume_fact.value),
            cash_cost_per_unit=float(cost_fact.value),
            commodity_prices=[base_price * 0.75, base_price, base_price * 1.25],
            tax_rate=float(tax_fact.value),
            multiple=float(multiple_fact.value),
            net_debt=net_debt,
            shares_outstanding=shares,
        )
        rows = grid["rows"]
        bear_v, base_v, bull_v = rows[0]["value_per_share"], rows[1]["value_per_share"], rows[2]["value_per_share"]
        sourced_facts = [volume_fact, cost_fact, price_fact, tax_fact, multiple_fact]
        evidence_confidence = sum(float(fact.confidence) for fact in sourced_facts) / len(
            sourced_facts
        )
        operating_spread = (base_price - float(cost_fact.value)) / max(abs(base_price), 1e-9)
        probabilities = evidence_weighted_probabilities(
            evidence_confidence=evidence_confidence,
            directional_signal=operating_spread,
            downside_risk=max(0.0, -operating_spread),
        )
        weighted = probability_weighted_value(
            [
                Scenario("bear", probabilities["bear"], bear_v),
                Scenario("base", probabilities["base"], base_v),
                Scenario("bull", probabilities["bull"], bull_v),
            ]
        )
        expected = weighted["expected_value"]

        return {
            "ticker": company.ticker,
            "model_type": company.valuation_model,
            "status": "ok",
            "publishable": True,
            "current_price": current_price,
            "bear_value": bear_v,
            "base_value": base_v,
            "bull_value": bull_v,
            "expected_value": expected,
            "margin_of_safety": margin_of_safety(expected, current_price),
            "missing_inputs": [],
            "reverse_dcf": {},
            "sensitivity": grid,
            "moat": empty_moat_framework(
                company.company_type, company.factor_tags or [], company.special_risks or []
            ),
            "trace": {
                "method": company.valuation_model,
                "engine": self.key,
                "input_source": "financial_facts",
                "publishable": True,
                "status": "ok",
                "model_version": MODEL_VERSION,
                "scenario_style": "commodity_price_grid",
                "fact_ids": {
                    **snapshot.fact_ids(),
                    "production_volume": volume_fact.id,
                    "cash_cost_per_unit": cost_fact.id,
                    "commodity_price": price_fact.id,
                    "effective_tax_rate": tax_fact.id,
                    "commodity_earnings_multiple": multiple_fact.id,
                },
                "periods": snapshot.periods(),
                "commodity_sensitivity": grid,
                "probabilities": probabilities,
                "probability_method": "source_confidence_plus_operating_spread",
                "evidence_confidence": evidence_confidence,
                "weighted": weighted["trace"],
            },
        }
