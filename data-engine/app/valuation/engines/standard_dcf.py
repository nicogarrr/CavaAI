"""Standard FCFF DCF engine — only runs on coherent financial_facts snapshots."""

from __future__ import annotations

from app.valuation import (
    DCFInputs,
    ReverseDCFInputs,
    Scenario,
    probability_weighted_value,
    run_dcf,
    sensitivity_grid,
    solve_required_growth,
)
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
from app.valuation.moat_framework import empty_moat_framework
from app.valuation.scenario_definitions import mechanical_dcf_scenarios


class StandardDCFEngine(ValuationEngine):
    key = "standard_dcf"

    def value(self, context: ValuationContext) -> dict:
        company = context.company
        snapshot = context.snapshot
        current_price = context.current_price

        if not snapshot.coherent:
            result = insufficient_result(
                ticker=company.ticker,
                model_type=company.valuation_model,
                engine_key=self.key,
                current_price=current_price,
                missing_inputs=snapshot.missing_inputs,
                reason="Coherent financial snapshot required. Bootstrap assumptions are disabled.",
                snapshot=snapshot,
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
            if fcf is None:
                result = insufficient_result(
                    ticker=company.ticker,
                    model_type=company.valuation_model,
                    engine_key=self.key,
                    current_price=current_price,
                    missing_inputs=["normalized_fcf_or_fcf_margin"],
                    reason="FCF margin cannot be derived from the coherent snapshot.",
                    snapshot=snapshot,
                )
                result["moat"] = empty_moat_framework(
                    company.company_type, company.factor_tags or [], company.special_risks or []
                )
                return result
            margin = fcf / revenue

        growth = snapshot.value("revenue_growth")
        if growth is None:
            growth = default_growth(company)
            growth_source = "tag_default"
        else:
            growth_source = "financial_facts"

        growth = max(min(growth, 0.45), -0.15)
        margin = max(min(margin, 0.50), 0.01)
        wacc = default_wacc(company)
        terminal = default_terminal_growth(company)
        net_debt = snapshot.value("net_debt") or 0.0

        base_inputs = DCFInputs(
            revenue=revenue,
            revenue_growth=growth,
            fcf_margin=margin,
            wacc=wacc,
            terminal_growth=terminal,
            net_debt=net_debt,
            shares_outstanding=shares,
        )

        scenarios = mechanical_dcf_scenarios(growth, margin, wacc, terminal)
        scenario_results = {}
        for scenario in scenarios:
            result = run_dcf(
                DCFInputs(
                    revenue=revenue,
                    revenue_growth=float(scenario.assumptions["revenue_growth"]),
                    fcf_margin=float(scenario.assumptions["fcf_margin"]),
                    wacc=float(scenario.assumptions["wacc"]),
                    terminal_growth=float(scenario.assumptions["terminal_growth"]),
                    net_debt=net_debt,
                    shares_outstanding=shares,
                )
            )
            scenario_results[scenario.name] = {
                "definition": {
                    "name": scenario.name,
                    "probability": scenario.probability,
                    "drivers": scenario.drivers,
                    "description": scenario.description,
                    "assumptions": scenario.assumptions,
                },
                "value_per_share": result.value_per_share,
                "trace": result.trace,
            }

        weighted = probability_weighted_value(
            [
                Scenario(name, data["definition"]["probability"], data["value_per_share"])
                for name, data in scenario_results.items()
            ]
        )

        reverse = {}
        if current_price is not None and current_price > 0:
            reverse = solve_required_growth(
                ReverseDCFInputs(
                    market_price=current_price,
                    revenue=revenue,
                    fcf_margin=margin,
                    wacc=wacc,
                    terminal_growth=terminal,
                    net_debt=net_debt,
                    shares_outstanding=shares,
                )
            )

        sensitivity = sensitivity_grid(
            base_inputs,
            growth_values=[growth - 0.04, growth, growth + 0.04],
            wacc_values=[wacc - 0.01, wacc, wacc + 0.01],
        )

        expected = weighted["expected_value"]
        bear = scenario_results["bear"]["value_per_share"]
        base = scenario_results["base"]["value_per_share"]
        bull = scenario_results["bull"]["value_per_share"]

        return {
            "ticker": company.ticker,
            "model_type": company.valuation_model,
            "status": "ok",
            "publishable": True,
            "current_price": current_price,
            "bear_value": bear,
            "base_value": base,
            "bull_value": bull,
            "expected_value": expected,
            "margin_of_safety": margin_of_safety(expected, current_price),
            "missing_inputs": [],
            "reverse_dcf": reverse,
            "sensitivity": sensitivity,
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
                "growth_source": growth_source,
                "wacc_source": "tag_default",
                "scenario_style": "mechanical_mvp",
                "fact_ids": snapshot.fact_ids(),
                "periods": snapshot.periods(),
                "snapshot": {
                    "as_of": snapshot.as_of_period,
                    "income_statement": snapshot.income_statement,
                    "balance_sheet": snapshot.balance_sheet,
                    "shares": snapshot.shares_period,
                    "warnings": snapshot.warnings,
                },
                "scenarios": scenario_results,
                "weighted": weighted["trace"],
                "reverse_dcf": reverse.get("trace") if reverse else None,
            },
        }
