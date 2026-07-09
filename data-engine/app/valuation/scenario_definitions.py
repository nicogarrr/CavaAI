"""Causal scenario definitions for valuation engines.

Mechanical ±growth/±margin shifts remain available as a fallback, but engines
should prefer named causal scenarios when company-specific drivers exist.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ScenarioDefinition:
    name: str
    probability: float
    assumptions: dict = field(default_factory=dict)
    drivers: list[str] = field(default_factory=list)
    description: str = ""


def mechanical_dcf_scenarios(
    growth: float,
    margin: float,
    wacc: float,
    terminal: float,
) -> list[ScenarioDefinition]:
    """Legacy MVP scenarios — labeled as mechanical, not causal."""
    return [
        ScenarioDefinition(
            name="bear",
            probability=0.25,
            assumptions={
                "revenue_growth": max(growth - 0.08, -0.05),
                "fcf_margin": max(margin - 0.06, 0.02),
                "wacc": wacc + 0.02,
                "terminal_growth": terminal,
            },
            drivers=["mechanical_growth_down", "mechanical_margin_down", "mechanical_wacc_up"],
            description="Mechanical bear: growth -8pp, margin -6pp, WACC +2pp.",
        ),
        ScenarioDefinition(
            name="base",
            probability=0.50,
            assumptions={
                "revenue_growth": growth,
                "fcf_margin": margin,
                "wacc": wacc,
                "terminal_growth": terminal,
            },
            drivers=["base_case_inputs"],
            description="Base case using snapshot inputs.",
        ),
        ScenarioDefinition(
            name="bull",
            probability=0.25,
            assumptions={
                "revenue_growth": growth + 0.08,
                "fcf_margin": min(margin + 0.06, 0.45),
                "wacc": max(wacc - 0.01, terminal + 0.01),
                "terminal_growth": terminal,
            },
            drivers=["mechanical_growth_up", "mechanical_margin_up", "mechanical_wacc_down"],
            description="Mechanical bull: growth +8pp, margin +6pp, WACC -1pp.",
        ),
    ]


def speculative_causal_scenarios(
    growth: float,
    margin: float,
    wacc: float,
    terminal: float,
    dilution_pct: float = 0.0,
) -> list[ScenarioDefinition]:
    """Causal-leaning scenarios for pre-FCF / speculative names (ASTS-like)."""
    return [
        ScenarioDefinition(
            name="execution_delay_funding_stress",
            probability=0.30,
            assumptions={
                "revenue_growth": max(growth - 0.12, -0.05),
                "fcf_margin": max(margin - 0.08, 0.01),
                "wacc": wacc + 0.03,
                "terminal_growth": max(terminal - 0.005, 0.01),
                "extra_dilution_pct": max(dilution_pct, 0.15),
            },
            drivers=["launch_or_deployment_delay", "higher_capex", "equity_raise", "higher_cost_of_capital"],
            description="Delays, higher funding need, and dilution compress equity value.",
        ),
        ScenarioDefinition(
            name="base_commercialization",
            probability=0.45,
            assumptions={
                "revenue_growth": growth,
                "fcf_margin": margin,
                "wacc": wacc,
                "terminal_growth": terminal,
                "extra_dilution_pct": dilution_pct,
            },
            drivers=["planned_ramp", "known_funding_gap"],
            description="Commercialization proceeds roughly as currently evidenced.",
        ),
        ScenarioDefinition(
            name="accelerated_monetization",
            probability=0.25,
            assumptions={
                "revenue_growth": growth + 0.10,
                "fcf_margin": min(margin + 0.05, 0.35),
                "wacc": max(wacc - 0.015, terminal + 0.015),
                "terminal_growth": terminal,
                "extra_dilution_pct": max(dilution_pct * 0.5, 0.0),
            },
            drivers=["faster_deployment", "government_or_mno_upside", "lower_financing_risk"],
            description="Faster ramp with reduced financing stress.",
        ),
    ]


def holding_company_scenarios(
    nav_per_share: float,
    holding_discount: float = 0.15,
) -> list[ScenarioDefinition]:
    return [
        ScenarioDefinition(
            name="bear",
            probability=0.25,
            assumptions={"nav_per_share": nav_per_share, "holding_discount": min(holding_discount + 0.15, 0.45)},
            drivers=["wider_holding_discount", "asset_value_compression"],
            description="Wider conglomerate/holding discount.",
        ),
        ScenarioDefinition(
            name="base",
            probability=0.50,
            assumptions={"nav_per_share": nav_per_share, "holding_discount": holding_discount},
            drivers=["base_nav", "base_discount"],
            description="Base NAV with standard holding discount.",
        ),
        ScenarioDefinition(
            name="bull",
            probability=0.25,
            assumptions={"nav_per_share": nav_per_share * 1.12, "holding_discount": max(holding_discount - 0.08, 0.0)},
            drivers=["nav_expansion", "discount_narrowing", "buybacks"],
            description="NAV expansion and discount narrowing.",
        ),
    ]
