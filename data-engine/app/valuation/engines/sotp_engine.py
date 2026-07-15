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
from app.valuation.scenario_model import Scenario, probability_weighted_value
from app.valuation.sotp import run_sotp
from sqlalchemy import desc, select

class SOTPEngine(ValuationEngine):
    key = "sotp"

    def value(self, context: ValuationContext) -> dict:
        company = context.company
        snapshot = context.snapshot
        current_price = context.current_price

        facts = list(
            context.db.scalars(
                select(FinancialFact)
                .where(FinancialFact.company_id == company.id)
                .order_by(FinancialFact.fiscal_year.desc().nullslast(), desc(FinancialFact.created_at))
            ).all()
        )
        latest_by_metric: dict[str, FinancialFact] = {}
        for fact in facts:
            latest_by_metric.setdefault(fact.metric, fact)
        shares_fact = latest_by_metric.get("shares_diluted")
        net_debt_fact = latest_by_metric.get("net_debt")
        shares = float(shares_fact.value) if shares_fact is not None else None
        net_debt = float(net_debt_fact.value) if net_debt_fact is not None else None

        segments: list[dict] = []
        missing_segments: list[str] = []
        segment_sources: list[FinancialFact] = []
        suffix = "_valuation_multiple"
        for multiple_metric, multiple_fact in latest_by_metric.items():
            if not multiple_metric.startswith("segment_") or not multiple_metric.endswith(suffix):
                continue
            prefix = multiple_metric[: -len(suffix)]
            operating_metric = f"{prefix}_operating_metric"
            operating_fact = latest_by_metric.get(operating_metric)
            if operating_fact is None or float(operating_fact.value) <= 0:
                missing_segments.append(operating_metric)
                continue
            if float(multiple_fact.value) <= 0:
                missing_segments.append(multiple_metric)
                continue
            segment_name = prefix.removeprefix("segment_")
            segments.append(
                {
                    "name": segment_name,
                    "metric": float(operating_fact.value),
                    "multiple": float(multiple_fact.value),
                    "metric_fact_id": operating_fact.id,
                    "multiple_fact_id": multiple_fact.id,
                    "period": operating_fact.period,
                }
            )
            segment_sources.extend([operating_fact, multiple_fact])

        discount_fact = latest_by_metric.get("holding_company_discount")

        missing: list[str] = []
        if shares is None or shares <= 0:
            missing.append("shares_diluted")
        if net_debt is None:
            missing.append("net_debt")
        if discount_fact is None or not 0 <= float(discount_fact.value) < 1:
            missing.append("holding_company_discount")
        if not segments:
            missing.extend(
                missing_segments
                or ["segment_*_operating_metric", "segment_*_valuation_multiple"]
            )

        if missing or not segments or shares is None or shares <= 0 or net_debt is None:
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
                    "segment_fact_contract": {
                        "operating_metric": "segment_{name}_operating_metric",
                        "valuation_multiple": "segment_{name}_valuation_multiple",
                    },
                    "found_segments": [s["name"] for s in segments],
                },
            )
            result["moat"] = empty_moat_framework(
                company.company_type, company.factor_tags or [], company.special_risks or []
            )
            return result

        assert discount_fact is not None
        base = run_sotp(segments, net_debt=net_debt, shares_outstanding=shares)
        nav_per_share = base["value_per_share"]
        discount = float(discount_fact.value)
        confidence_sources = segment_sources + [discount_fact]
        if shares_fact is not None:
            confidence_sources.append(shares_fact)
        if net_debt_fact is not None:
            confidence_sources.append(net_debt_fact)
        evidence_confidence = sum(float(fact.confidence) for fact in confidence_sources) / len(
            confidence_sources
        )
        scenarios = holding_company_scenarios(
            nav_per_share,
            holding_discount=discount,
            evidence_confidence=evidence_confidence,
        )

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

        weighted = probability_weighted_value(
            [
                Scenario(s["definition"]["name"], s["definition"]["probability"], s["value_per_share"])
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
                "fact_ids": {
                    **snapshot.fact_ids(),
                    "shares_diluted": shares_fact.id if shares_fact else None,
                    "net_debt": net_debt_fact.id if net_debt_fact else None,
                    "holding_company_discount": discount_fact.id,
                    **{
                        f"segment_{segment['name']}_operating_metric": segment["metric_fact_id"]
                        for segment in segments
                    },
                    **{
                        f"segment_{segment['name']}_valuation_multiple": segment["multiple_fact_id"]
                        for segment in segments
                    },
                },
                "periods": {
                    **snapshot.periods(),
                    "shares_diluted": shares_fact.period if shares_fact else None,
                    "net_debt": net_debt_fact.period if net_debt_fact else None,
                    "holding_company_discount": discount_fact.period,
                    **{
                        f"segment_{segment['name']}": segment["period"]
                        for segment in segments
                    },
                },
                "snapshot": {
                    "as_of": snapshot.as_of_period,
                    "income_statement": snapshot.income_statement,
                    "balance_sheet": snapshot.balance_sheet,
                    "shares": snapshot.shares_period,
                    "warnings": snapshot.warnings,
                },
                "sotp": base,
                "holding_discount_base": discount,
                "holding_discount_source": "financial_facts",
                "probability_method": "source_confidence_plus_holding_discount",
                "evidence_confidence": evidence_confidence,
                "missing_optional_segments": missing_segments,
                "scenarios": scenario_results,
                "weighted": weighted["trace"],
            },
        }
