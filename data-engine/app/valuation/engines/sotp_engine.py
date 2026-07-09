"""Sum-of-the-parts engine for multi-segment / holding-style names."""

from __future__ import annotations

from app.models import FinancialFact
from app.valuation.engines.base import (
    MODEL_VERSION,
    ValuationContext,
    ValuationEngine,
    insufficient_result,
    margin_of_safety,
)
from app.valuation.moat_framework import empty_moat_framework
from app.valuation.scenario_definitions import holding_company_scenarios
from app.valuation.sotp import run_sotp
from sqlalchemy import desc, select


# Default segment templates keyed by ticker when segment facts are not yet ingested.
# Values are placeholders only used when matching FinancialFact metrics exist.
SEGMENT_TEMPLATES: dict[str, list[dict]] = {
    "BN": [
        {"name": "asset_management", "metric_key": "fee_related_earnings", "multiple": 18.0},
        {"name": "insurance", "metric_key": "insurance_earnings", "multiple": 12.0},
        {"name": "invested_capital", "metric_key": "invested_capital", "multiple": 1.0},
    ],
    "BABA": [
        {"name": "china_commerce", "metric_key": "china_commerce_revenue", "multiple": 1.5},
        {"name": "cloud", "metric_key": "cloud_revenue", "multiple": 4.0},
        {"name": "international", "metric_key": "international_revenue", "multiple": 2.0},
        {"name": "local_services", "metric_key": "local_services_revenue", "multiple": 1.2},
    ],
    "RKLB": [
        {"name": "launch", "metric_key": "launch_revenue", "multiple": 4.0},
        {"name": "space_systems", "metric_key": "space_systems_revenue", "multiple": 5.0},
    ],
}


class SOTPEngine(ValuationEngine):
    key = "sotp"

    def value(self, context: ValuationContext) -> dict:
        company = context.company
        snapshot = context.snapshot
        current_price = context.current_price
        shares = snapshot.value("shares_diluted")
        net_debt = snapshot.value("net_debt")

        templates = SEGMENT_TEMPLATES.get(company.ticker.upper(), [])
        segments: list[dict] = []
        missing_segments: list[str] = []

        for template in templates:
            fact = context.db.scalar(
                select(FinancialFact)
                .where(
                    FinancialFact.company_id == company.id,
                    FinancialFact.metric == template["metric_key"],
                )
                .order_by(FinancialFact.fiscal_year.desc().nullslast(), desc(FinancialFact.created_at))
                .limit(1)
            )
            if fact is None or float(fact.value) <= 0:
                missing_segments.append(template["metric_key"])
                continue
            segments.append(
                {
                    "name": template["name"],
                    "metric": float(fact.value),
                    "multiple": template["multiple"],
                    "fact_id": fact.id,
                    "period": fact.period,
                }
            )

        missing = list(snapshot.missing_inputs)
        if shares is None or shares <= 0:
            missing.append("shares_diluted")
        if not segments:
            missing.extend(missing_segments or ["segment_operating_metrics"])
            missing.append("sotp_segment_facts")

        if missing or not segments or shares is None or shares <= 0:
            result = insufficient_result(
                ticker=company.ticker,
                model_type=company.valuation_model,
                engine_key=self.key,
                current_price=current_price,
                missing_inputs=sorted(set(missing)),
                reason=(
                    "SOTP requires coherent shares/net-debt plus segment-level facts. "
                    "Do not fall back to a single-firm DCF for holding/multi-segment names."
                ),
                snapshot=snapshot,
                extra_trace={
                    "required_segments": [t["metric_key"] for t in templates] or ["segment_metrics"],
                    "found_segments": [s["name"] for s in segments],
                },
            )
            result["moat"] = empty_moat_framework(
                company.company_type, company.factor_tags or [], company.special_risks or []
            )
            return result

        base = run_sotp(segments, net_debt=net_debt or 0.0, shares_outstanding=shares)
        nav_per_share = base["value_per_share"]
        discount = 0.15 if "china" in (company.factor_tags or []) or company.ticker == "BABA" else 0.10
        scenarios = holding_company_scenarios(nav_per_share, holding_discount=discount)

        scenario_results = {}
        for scenario in scenarios:
            nav = float(scenario.assumptions["nav_per_share"])
            disc = float(scenario.assumptions["holding_discount"])
            value = nav * (1.0 - disc)
            scenario_results[scenario.name] = {
                "definition": {
                    "name": scenario.name,
                    "probability": scenario.probability,
                    "drivers": scenario.drivers,
                    "description": scenario.description,
                    "assumptions": scenario.assumptions,
                },
                "value_per_share": value,
            }

        from app.valuation import Scenario as ProbScenario, probability_weighted_value

        weighted = probability_weighted_value(
            [
                ProbScenario(s["definition"]["name"], s["definition"]["probability"], s["value_per_share"])
                for s in scenario_results.values()
            ]
        )
        expected = weighted["expected_value"]

        return {
            "ticker": company.ticker,
            "model_type": company.valuation_model,
            "status": "ok",
            "publishable": True,
            "current_price": current_price,
            "bear_value": scenario_results["bear"]["value_per_share"],
            "base_value": scenario_results["base"]["value_per_share"],
            "bull_value": scenario_results["bull"]["value_per_share"],
            "expected_value": expected,
            "margin_of_safety": margin_of_safety(expected, current_price),
            "missing_inputs": missing_segments,
            "reverse_dcf": {},
            "sensitivity": {"rows": []},
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
                "scenario_style": "holding_discount_on_sotp",
                "fact_ids": snapshot.fact_ids(),
                "periods": snapshot.periods(),
                "snapshot": {
                    "as_of": snapshot.as_of_period,
                    "income_statement": snapshot.income_statement,
                    "balance_sheet": snapshot.balance_sheet,
                    "shares": snapshot.shares_period,
                    "warnings": snapshot.warnings,
                },
                "sotp": base,
                "holding_discount_base": discount,
                "missing_optional_segments": missing_segments,
                "scenarios": scenario_results,
                "weighted": weighted["trace"],
            },
        }
