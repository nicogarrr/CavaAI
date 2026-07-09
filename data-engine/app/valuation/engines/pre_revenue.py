"""Pre-revenue / speculative scenario engine with funding-gap dilution."""

from __future__ import annotations

from app.valuation.dcf_fcff import DCFInputs, run_dcf
from app.valuation.engines.base import (
    MODEL_VERSION,
    ValuationContext,
    ValuationEngine,
    default_growth,
    default_terminal_growth,
    default_wacc,
    insufficient_result,
    margin_of_safety,
)
from app.valuation.funding_gap import estimate_funding_gap
from app.valuation.moat_framework import empty_moat_framework
from app.valuation.reverse_dcf import ReverseDCFInputs, solve_required_growth
from app.valuation.scenario_definitions import speculative_causal_scenarios
from app.valuation.scenario_model import Scenario, probability_weighted_value
from app.valuation.sensitivity import sensitivity_grid


class PreRevenueScenarioEngine(ValuationEngine):
    """For ASTS-like names: requires facts; applies causal scenarios + funding gap."""

    key = "pre_revenue"

    def value(self, context: ValuationContext) -> dict:
        company = context.company
        snapshot = context.snapshot
        current_price = context.current_price

        # Still refuse bootstrap — speculative names need at least revenue + shares.
        if not snapshot.coherent:
            result = insufficient_result(
                ticker=company.ticker,
                model_type=company.valuation_model,
                engine_key=self.key,
                current_price=current_price,
                missing_inputs=snapshot.missing_inputs
                + [
                    "deployment_curve_or_capacity_plan",
                    "funding_plan",
                    "dilution_schedule",
                ],
                reason=(
                    "Pre-revenue/speculative valuation requires a coherent financial snapshot "
                    "plus operational drivers. Generic bootstrap DCF is disabled."
                ),
                snapshot=snapshot,
                extra_trace={
                    "required_operational_inputs": [
                        "satellites_or_capacity_deployed",
                        "revenue_ramp",
                        "constellation_capex",
                        "financing_and_dilution",
                    ]
                },
            )
            result["moat"] = empty_moat_framework(
                company.company_type, company.factor_tags or [], company.special_risks or []
            )
            return result

        revenue = snapshot.value("revenue")
        shares = snapshot.value("shares_diluted")
        assert revenue is not None and shares is not None

        margin = snapshot.value("fcf_margin")
        if margin is None:
            fcf = snapshot.value("free_cash_flow")
            if fcf is None or revenue <= 0:
                result = insufficient_result(
                    ticker=company.ticker,
                    model_type=company.valuation_model,
                    engine_key=self.key,
                    current_price=current_price,
                    missing_inputs=["normalized_fcf_or_fcf_margin"],
                    reason="Cannot derive FCF margin for speculative scenario DCF.",
                    snapshot=snapshot,
                )
                result["moat"] = empty_moat_framework(
                    company.company_type, company.factor_tags or [], company.special_risks or []
                )
                return result
            margin = fcf / revenue

        # Near-zero revenue speculative names: still allow but flag low confidence.
        growth = snapshot.value("revenue_growth")
        growth_source = "financial_facts" if growth is not None else "tag_default"
        if growth is None:
            growth = default_growth(company)

        growth = max(min(growth, 0.60), -0.15)
        # Allow thinner / negative-ish margins for early stage but clamp for DCF math.
        margin = max(min(margin, 0.40), 0.01)
        wacc = default_wacc(company)
        terminal = default_terminal_growth(company)
        net_debt = snapshot.value("net_debt") or 0.0

        # Preliminary base for funding-gap dilution estimate.
        base_preview = run_dcf(
            DCFInputs(
                revenue=max(revenue, 1.0),
                revenue_growth=growth,
                fcf_margin=margin,
                wacc=wacc,
                terminal_growth=terminal,
                net_debt=net_debt,
                shares_outstanding=shares,
            )
        )
        funding = estimate_funding_gap(
            snapshot,
            current_price=current_price,
            value_per_share=base_preview.value_per_share,
        )
        dilution_pct = 0.0
        if funding.dilution:
            dilution_pct = float(funding.dilution.get("dilution_pct") or 0.0)

        scenarios = speculative_causal_scenarios(growth, margin, wacc, terminal, dilution_pct)
        scenario_results = {}
        for scenario in scenarios:
            dcf = run_dcf(
                DCFInputs(
                    revenue=max(revenue, 1.0),
                    revenue_growth=float(scenario.assumptions["revenue_growth"]),
                    fcf_margin=float(scenario.assumptions["fcf_margin"]),
                    wacc=float(scenario.assumptions["wacc"]),
                    terminal_growth=float(scenario.assumptions["terminal_growth"]),
                    net_debt=net_debt,
                    shares_outstanding=shares,
                )
            )
            extra_dilution = float(scenario.assumptions.get("extra_dilution_pct") or 0.0)
            value = dcf.value_per_share * (1.0 - min(extra_dilution, 0.80))
            scenario_results[scenario.name] = {
                "definition": {
                    "name": scenario.name,
                    "probability": scenario.probability,
                    "drivers": scenario.drivers,
                    "description": scenario.description,
                    "assumptions": scenario.assumptions,
                },
                "value_per_share": value,
                "undiluted_value_per_share": dcf.value_per_share,
                "trace": dcf.trace,
            }

        # Map causal names to bear/base/bull for API compatibility.
        ordered = list(scenario_results.values())
        bear_v = ordered[0]["value_per_share"]
        base_v = ordered[1]["value_per_share"]
        bull_v = ordered[2]["value_per_share"]

        weighted = probability_weighted_value(
            [
                Scenario(s["definition"]["name"], s["definition"]["probability"], s["value_per_share"])
                for s in ordered
            ]
        )
        expected = weighted["expected_value"]

        reverse = {}
        if current_price is not None and current_price > 0:
            reverse = solve_required_growth(
                ReverseDCFInputs(
                    market_price=current_price,
                    revenue=max(revenue, 1.0),
                    fcf_margin=margin,
                    wacc=wacc,
                    terminal_growth=terminal,
                    net_debt=net_debt,
                    shares_outstanding=shares,
                )
            )

        sensitivity = sensitivity_grid(
            DCFInputs(
                revenue=max(revenue, 1.0),
                revenue_growth=growth,
                fcf_margin=margin,
                wacc=wacc,
                terminal_growth=terminal,
                net_debt=net_debt,
                shares_outstanding=shares,
            ),
            growth_values=[growth - 0.05, growth, growth + 0.05],
            wacc_values=[wacc - 0.01, wacc, wacc + 0.02],
        )

        publishable = funding.status != "incomplete"
        status = "ok" if publishable else "partial"
        missing = list(funding.missing_inputs) if funding.status == "incomplete" else []

        return {
            "ticker": company.ticker,
            "model_type": company.valuation_model,
            "status": status,
            "publishable": publishable,
            "current_price": current_price,
            "bear_value": bear_v,
            "base_value": base_v,
            "bull_value": bull_v,
            "expected_value": expected,
            "margin_of_safety": margin_of_safety(expected, current_price),
            "missing_inputs": missing,
            "reverse_dcf": reverse,
            "sensitivity": sensitivity,
            "moat": empty_moat_framework(
                company.company_type, company.factor_tags or [], company.special_risks or []
            ),
            "trace": {
                "method": company.valuation_model,
                "engine": self.key,
                "input_source": "financial_facts",
                "publishable": publishable,
                "status": status,
                "model_version": MODEL_VERSION,
                "growth_source": growth_source,
                "scenario_style": "causal_speculative",
                "fact_ids": snapshot.fact_ids(),
                "periods": snapshot.periods(),
                "snapshot": {
                    "as_of": snapshot.as_of_period,
                    "income_statement": snapshot.income_statement,
                    "balance_sheet": snapshot.balance_sheet,
                    "shares": snapshot.shares_period,
                    "warnings": snapshot.warnings,
                },
                "funding_gap": {
                    "status": funding.status,
                    "funding_gap": funding.funding_gap,
                    "available_cash": funding.available_cash,
                    "planned_capex": funding.planned_capex,
                    "burn_proxy": funding.burn_proxy,
                    "min_cash_buffer": funding.min_cash_buffer,
                    "missing_inputs": funding.missing_inputs,
                    "dilution": funding.dilution,
                },
                "scenarios": scenario_results,
                "weighted": weighted["trace"],
                "notice": (
                    None
                    if publishable
                    else "Scenario values computed but funding-gap dilution is incomplete; treat as non-final."
                ),
            },
        }
