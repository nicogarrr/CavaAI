"""TAM / SAM / SOM and capacity-aware market opportunity analysis.

This is the single canonical home for market size, penetration, market share and
valuation-implied share. The long-term model consumes it instead of maintaining a
separate market-share calculation. For mature asset-heavy businesses the same
contract becomes a reinvestment-runway review.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, FinancialFact
from app.services.company_framework import CompanyFramework


MARKET_METRICS = (
    "tam",
    "total_addressable_market",
    "sam",
    "serviceable_market",
    "som",
    "captureable_market",
    "market_size",
    "sector_revenue",
    "market_growth",
    "sector_growth",
    "company_market_share",
    "market_share",
    "historical_max_market_share",
    "peer_leader_market_share",
    "asset_base",
    "reinvestment_rate",
    "incremental_roic",
    "asset_value",
    "nav",
    "holdco_debt",
    "addressable_subscribers",
    "subscribers",
    "active_accounts",
    "penetration",
    "monthly_arpu",
    "arpu",
    "revenue_share",
    "satellites",
    "capacity_per_satellite",
    "capacity_units",
    "utilization",
    "price_per_gb",
    "price_per_unit",
    "launches",
    "price_per_launch",
    "backlog",
    "backlog_conversion",
    "customers",
    "seats",
    "arr",
    "tpv",
    "take_rate",
    "bookings",
    "trips",
    "revenue_per_trip",
    "stores",
    "sales_per_store",
    "production_volume",
    "realized_price",
    "royalty_rate",
)


@dataclass(frozen=True)
class FormulaDefinition:
    key: str
    label: str
    input_metrics: tuple[str, ...]
    calculate: Callable[[dict[str, float]], float]
    note: str


def _finite(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if isfinite(parsed) else None


def _unique_ids(*facts: FinancialFact | None, ids: list[int] | None = None) -> list[int]:
    result: list[int] = []
    for fact_id in ids or []:
        if fact_id not in result:
            result.append(fact_id)
    for fact in facts:
        if fact is not None and fact.id not in result:
            result.append(fact.id)
    return result


def _evidence(fact: FinancialFact | None) -> dict[str, Any] | None:
    if fact is None:
        return None
    return {
        "fact_id": fact.id,
        "metric": fact.metric,
        "period": fact.period,
        "fiscal_year": fact.fiscal_year,
        "document_id": fact.source_id,
        "source_type": fact.source_type,
        "confidence": _finite(fact.confidence),
        "reported": fact.is_reported,
        "adjusted": fact.is_adjusted,
    }


def _annual_by_year(facts: list[FinancialFact]) -> dict[int, FinancialFact]:
    result: dict[int, FinancialFact] = {}
    for fact in facts:
        quarter = (fact.fiscal_quarter or "").upper()
        period = (fact.period or "").upper()
        if fact.fiscal_year is None or quarter.startswith("Q") or period.startswith("Q"):
            continue
        result[int(fact.fiscal_year)] = fact
    return result


class MarketOpportunityEngine:
    """Build one coherent market opportunity view for a company framework."""

    @staticmethod
    def metrics_for_framework(framework: CompanyFramework) -> set[str]:
        return set(MARKET_METRICS) | set(framework.required_fact_metrics)

    def build(
        self,
        db: Session,
        company: Company,
        framework: CompanyFramework,
        *,
        fact_cache: dict[str, list[FinancialFact]],
        revenue_history: dict[int, FinancialFact],
        base_scenario: dict[str, Any] | None,
        reverse_dcf: dict[str, Any],
        horizon: int,
    ) -> dict[str, Any]:
        market = self._market_series(fact_cache)
        top_down = self._top_down(
            fact_cache=fact_cache,
            revenue_history=revenue_history,
            market=market,
            base_scenario=base_scenario,
            horizon=horizon,
        )
        bottom_up = self._bottom_up(fact_cache, framework)
        implied = self._implied_share(
            fact_cache=fact_cache,
            revenue_history=revenue_history,
            market=market,
            top_down=top_down,
            base_scenario=base_scenario,
            reverse_dcf=reverse_dcf,
            horizon=horizon,
        )
        constraints = self._constraints(
            framework=framework,
            top_down=top_down,
            bottom_up=bottom_up,
            base_scenario=base_scenario,
        )
        verdict = self._verdict(top_down, bottom_up, implied, base_scenario)
        source_fact_ids = _unique_ids(ids=(top_down["source_fact_ids"] + bottom_up["source_fact_ids"] + implied["source_fact_ids"]))

        if framework.market_opportunity_mode == "reinvestment_runway":
            status = "runway_review" if source_fact_ids else "insufficient_data"
            conclusion = (
                "TAM is secondary for this framework; evaluate reinvestment runway, asset base and capital allocation."
            )
        else:
            status = "ok" if top_down["status"] in {"partial", "ok"} or bottom_up["status"] == "ok" else "insufficient_data"
            conclusion = verdict["conclusion"]

        return {
            "status": status,
            "framework": framework.key,
            "mode": framework.market_opportunity_mode,
            "primary_question": framework.primary_question,
            "top_down": top_down,
            "bottom_up": bottom_up,
            "implied_by_valuation": implied,
            "market_share": {
                "status": implied["status"],
                "conclusion": implied["conclusion"],
                "confidence": implied["confidence"],
                "current_market_share": implied["current_market_share"],
                "prior_market_share": implied["prior_market_share"],
                "base_future_market_share": implied["base_future_market_share"],
                "valuation_implied_market_share": implied["valuation_implied_market_share"],
                "source_fact_ids": implied["source_fact_ids"],
                "missing_inputs": implied["missing_inputs"],
            },
            "constraints": constraints,
            "verdict": verdict,
            "source_fact_ids": source_fact_ids,
            "missing_inputs": sorted(set(top_down["missing_inputs"] + bottom_up["missing_inputs"] + implied["missing_inputs"])),
            "note": "Top-down and bottom-up are compared only when both have sourced inputs; otherwise the result remains partial or unknown.",
        }

    def _market_series(self, fact_cache: dict[str, list[FinancialFact]]) -> dict[str, Any]:
        aliases = {
            "tam": ("tam", "total_addressable_market", "market_size"),
            "sam": ("sam", "serviceable_market"),
            "som": ("som", "captureable_market"),
            "sector": ("sector_revenue",),
            "growth": ("market_growth", "sector_growth"),
            "share": ("company_market_share", "market_share"),
        }
        selected: dict[str, dict[int, FinancialFact]] = {}
        for key, metric_names in aliases.items():
            facts: list[FinancialFact] = []
            for metric in metric_names:
                facts.extend(fact_cache.get(metric, []))
            selected[key] = _annual_by_year(facts)
        return selected

    def _latest(self, facts: dict[int, FinancialFact], year: int | None = None) -> FinancialFact | None:
        if year is not None and year in facts:
            return facts[year]
        return facts[max(facts)] if facts else None

    def _top_down(
        self,
        *,
        fact_cache: dict[str, list[FinancialFact]],
        revenue_history: dict[int, FinancialFact],
        market: dict[str, dict[int, FinancialFact]],
        base_scenario: dict[str, Any] | None,
        horizon: int,
    ) -> dict[str, Any]:
        market_fact = self._latest(market["tam"])
        sector_fact = self._latest(market["sector"])
        anchor = market_fact or sector_fact
        anchor_kind = "tam" if market_fact else "sector_revenue" if sector_fact else None
        sam_fact = self._latest(market["sam"])
        som_fact = self._latest(market["som"])
        growth_fact = self._latest(market["growth"])
        source_fact_ids = _unique_ids(anchor, sam_fact, som_fact, growth_fact)
        missing: list[str] = []
        if anchor is None:
            missing.append("tam_or_sector_revenue")
        if growth_fact is None:
            missing.append("market_growth")
        if som_fact is None:
            missing.append("som_or_captureable_market")

        anchor_value = _finite(anchor.value) if anchor else None
        market_growth = _finite(growth_fact.value) if growth_fact else None
        future_market = None
        if anchor_value is not None and market_growth is not None:
            future_market = anchor_value * (1 + market_growth) ** horizon

        current_year = max(revenue_history) if revenue_history else None
        current_revenue = _finite(revenue_history[current_year].value) if current_year is not None else None
        current_share = None
        current_share_basis = "missing"
        current_market_fact = self._latest(market["sector"], current_year) or self._latest(market["tam"], current_year)
        direct_share = self._latest(market["share"], current_year)
        if direct_share is not None:
            current_share = _finite(direct_share.value)
            current_share_basis = "reported_company_market_share"
            source_fact_ids = _unique_ids(direct_share, ids=source_fact_ids)
        elif current_market_fact is not None and current_revenue is not None and _finite(current_market_fact.value) not in (None, 0):
            current_share = current_revenue / (_finite(current_market_fact.value) or 1)
            current_share_basis = "revenue_divided_by_aligned_market_fact"
            source_fact_ids = _unique_ids(current_market_fact, revenue_history[current_year], ids=source_fact_ids)

        return {
            "status": "ok" if anchor is not None and growth_fact is not None else "insufficient_data",
            "market_type": anchor_kind,
            "tam": {"value": anchor_value, "unit": anchor.unit if anchor else "USD", "source_fact_ids": _unique_ids(anchor)},
            "sam": self._fact_output(sam_fact),
            "som": self._fact_output(som_fact),
            "market_growth": self._fact_output(growth_fact),
            "future_market": {"value": future_market, "year_offset": horizon, "source_fact_ids": source_fact_ids, "calculation": "anchor market × (1 + market growth)^horizon"},
            "current_market_share": current_share,
            "current_market_share_basis": current_share_basis,
            "source_fact_ids": source_fact_ids,
            "missing_inputs": missing,
        }

    def _bottom_up(self, fact_cache: dict[str, list[FinancialFact]], framework: CompanyFramework) -> dict[str, Any]:
        definitions = self._formula_definitions(framework)
        formulas: list[dict[str, Any]] = []
        all_missing: list[str] = []
        for definition in definitions:
            inputs: dict[str, float] = {}
            input_facts: list[FinancialFact] = []
            missing: list[str] = []
            for metric in definition.input_metrics:
                fact = self._latest_from_metric(fact_cache, metric)
                value = _finite(fact.value) if fact else None
                if fact is None or value is None:
                    missing.append(metric)
                else:
                    inputs[metric] = value
                    input_facts.append(fact)
            if missing:
                all_missing.extend(missing)
                formulas.append({"key": definition.key, "label": definition.label, "status": "insufficient_data", "value": None, "missing_inputs": missing, "source_fact_ids": _unique_ids(ids=[fact.id for fact in input_facts]), "note": definition.note})
                continue
            value = definition.calculate(inputs)
            formulas.append({"key": definition.key, "label": definition.label, "status": "calculated", "value": value, "inputs": inputs, "source_fact_ids": _unique_ids(ids=[fact.id for fact in input_facts]), "formula": " × ".join(definition.input_metrics), "note": definition.note})

        available = [item for item in formulas if item["value"] is not None]
        return {
            "status": "ok" if available else "insufficient_data",
            "formulas": formulas,
            "value": min(item["value"] for item in available) if available else None,
            "binding_basis": "minimum available bottom-up capacity/opportunity estimate",
            "source_fact_ids": _unique_ids(ids=[fact_id for item in formulas for fact_id in item.get("source_fact_ids", [])]),
            "missing_inputs": sorted(set(all_missing)),
        }

    def _implied_share(
        self,
        *,
        fact_cache: dict[str, list[FinancialFact]],
        revenue_history: dict[int, FinancialFact],
        market: dict[str, dict[int, FinancialFact]],
        top_down: dict[str, Any],
        base_scenario: dict[str, Any] | None,
        reverse_dcf: dict[str, Any],
        horizon: int,
    ) -> dict[str, Any]:
        market_fact = self._latest(market["tam"]) or self._latest(market["sector"])
        growth_fact = self._latest(market["growth"])
        current_year = max(revenue_history) if revenue_history else None
        current_market_share = top_down["current_market_share"]
        prior_market_share = None
        common_years = sorted(set(revenue_history) & set(market["tam"]).union(market["sector"]))
        if len(common_years) >= 2:
            prior_year = common_years[-2]
            prior_market = self._latest(market["sector"], prior_year) or self._latest(market["tam"], prior_year)
            prior_revenue = revenue_history[prior_year]
            if prior_market and _finite(prior_market.value) not in (None, 0):
                prior_market_share = (_finite(prior_revenue.value) or 0) / (_finite(prior_market.value) or 1)

        future_market = top_down["future_market"]["value"]
        base_revenue = base_scenario.get("terminal_year", {}).get("revenue") if base_scenario else None
        base_future_share = base_revenue / future_market if base_revenue is not None and future_market not in (None, 0) else None
        current_revenue = _finite(revenue_history[current_year].value) if current_year is not None else None
        required_revenue = None
        if reverse_dcf.get("status") == "ok" and current_revenue is not None:
            required_revenue = current_revenue * (1 + reverse_dcf["required_revenue_growth"]) ** horizon
        valuation_share = required_revenue / future_market if required_revenue is not None and future_market not in (None, 0) else None
        source_fact_ids = _unique_ids(market_fact, growth_fact, ids=top_down["source_fact_ids"])
        if current_year is not None:
            source_fact_ids = _unique_ids(revenue_history[current_year], ids=source_fact_ids)

        missing: list[str] = []
        if market_fact is None:
            missing.append("tam_or_sector_revenue")
        if growth_fact is None:
            missing.append("market_growth")
        if base_future_share is None:
            missing.append("future_market_or_base_revenue")
        conclusion = "unknown"
        if prior_market_share is not None and current_market_share is not None:
            conclusion = "gana cuota" if current_market_share > prior_market_share else "pierde cuota" if current_market_share < prior_market_share else "mantiene cuota"
        elif base_future_share is not None:
            conclusion = "cuota futura calculada"
        return {
            "status": "ok" if base_future_share is not None else "insufficient_data",
            "conclusion": conclusion,
            "confidence": "medium" if source_fact_ids and base_future_share is not None else "low",
            "current_market_share": current_market_share,
            "prior_market_share": prior_market_share,
            "base_future_market_share": base_future_share,
            "valuation_implied_market_share": valuation_share,
            "base_future_revenue": base_revenue,
            "valuation_required_revenue": required_revenue,
            "source_fact_ids": source_fact_ids,
            "missing_inputs": missing,
        }

    def _constraints(
        self,
        *,
        framework: CompanyFramework,
        top_down: dict[str, Any],
        bottom_up: dict[str, Any],
        base_scenario: dict[str, Any] | None,
    ) -> dict[str, Any]:
        base_revenue = base_scenario.get("terminal_year", {}).get("revenue") if base_scenario else None
        candidates: list[dict[str, Any]] = []
        top_value = top_down["future_market"]["value"]
        if top_value is not None:
            candidates.append({"constraint": "market_size", "capacity": top_value, "source_fact_ids": top_down["source_fact_ids"]})
        if bottom_up["value"] is not None:
            candidates.append({"constraint": "operating_capacity", "capacity": bottom_up["value"], "source_fact_ids": bottom_up["source_fact_ids"]})
        binding = None
        if candidates:
            binding = min(candidates, key=lambda item: item["capacity"])
        if binding and base_revenue is not None:
            if binding["capacity"] < base_revenue:
                conclusion = f"{binding['constraint']} is below the base revenue target."
                severity = "binding"
            else:
                conclusion = "No sourced capacity constraint is below the base revenue target."
                severity = "not_binding"
        elif binding:
            conclusion = "A candidate constraint exists, but the base revenue target is unavailable."
            severity = "unknown"
        else:
            conclusion = "No sourced constraint can be ranked yet."
            severity = "unknown"
        return {
            "status": "ok" if binding else "insufficient_data",
            "binding_constraint": binding["constraint"] if binding else None,
            "severity": severity,
            "candidate_constraints": candidates,
            "framework_constraints": list(framework.binding_constraints),
            "conclusion": conclusion,
        }

    def _verdict(self, top_down: dict[str, Any], bottom_up: dict[str, Any], implied: dict[str, Any], base_scenario: dict[str, Any] | None) -> dict[str, Any]:
        base_revenue = base_scenario.get("terminal_year", {}).get("revenue") if base_scenario else None
        limits = [value for value in (top_down["future_market"]["value"], bottom_up["value"]) if value is not None]
        if base_revenue is None or not limits:
            return {"label": "unknown", "confidence": "low", "conclusion": "No hay evidencia suficiente para juzgar si el crecimiento cabe en el mercado y la capacidad."}
        binding_capacity = min(limits)
        ratio = base_revenue / binding_capacity if binding_capacity else None
        if ratio is None:
            label = "unknown"
        elif ratio <= 0.80:
            label = "reasonable"
        elif ratio <= 1.0:
            label = "aggressive_but_possible"
        else:
            label = "unrealistic_without_new_evidence"
        return {"label": label, "confidence": "medium", "base_revenue_to_binding_capacity": ratio, "conclusion": f"Base revenue uses {ratio:.1%} of the tightest sourced market/capacity estimate."}

    @staticmethod
    def _fact_output(fact: FinancialFact | None) -> dict[str, Any]:
        if fact is None:
            return {"value": None, "unit": "unknown", "status": "insufficient_data", "source_fact_ids": []}
        return {"value": _finite(fact.value), "unit": fact.unit, "status": "reported" if fact.is_reported else "calculated", "source_fact_ids": [fact.id], "period": fact.period, "document_id": fact.source_id, "source_type": fact.source_type}

    @staticmethod
    def _latest_from_metric(fact_cache: dict[str, list[FinancialFact]], metric: str) -> FinancialFact | None:
        facts = [fact for fact in fact_cache.get(metric, []) if fact.fiscal_year is not None]
        if not facts:
            return None
        return sorted(facts, key=lambda fact: (fact.fiscal_year or 0, fact.created_at))[-1]

    @staticmethod
    def _formula_definitions(framework: CompanyFramework) -> list[FormulaDefinition]:
        def monthly(value: dict[str, float]) -> float:
            return value.get("monthly_arpu", value.get("arpu", 0)) * 12

        definitions: dict[str, list[FormulaDefinition]] = {
            "space_network": [
                FormulaDefinition("subscriber_opportunity", "Subscribers × penetration × ARPU × share", ("addressable_subscribers", "penetration", "monthly_arpu", "revenue_share"), lambda v: v["addressable_subscribers"] * v["penetration"] * monthly(v) * v["revenue_share"], "Monthly ARPU is annualized ×12."),
                FormulaDefinition("satellite_capacity", "Satellites × capacity × utilization × price", ("satellites", "capacity_per_satellite", "utilization", "price_per_gb"), lambda v: v["satellites"] * v["capacity_per_satellite"] * v["utilization"] * v["price_per_gb"], "Physical capacity proxy; units must be compatible."),
            ],
            "space_defense": [
                FormulaDefinition("launch_opportunity", "Launches × price per launch", ("launches", "price_per_launch"), lambda v: v["launches"] * v["price_per_launch"], "Annual launch revenue capacity."),
                FormulaDefinition("backlog_conversion", "Backlog × conversion", ("backlog", "backlog_conversion"), lambda v: v["backlog"] * v["backlog_conversion"], "Backlog conversion is a sourced assumption, not a forecast default."),
            ],
            "platform": [
                FormulaDefinition("payments_opportunity", "TPV × take rate", ("tpv", "take_rate"), lambda v: v["tpv"] * v["take_rate"], "Platform monetization capacity."),
                FormulaDefinition("mobility_opportunity", "Trips × revenue per trip", ("trips", "revenue_per_trip"), lambda v: v["trips"] * v["revenue_per_trip"], "Mobility monetization capacity."),
            ],
            "subscriber": [
                FormulaDefinition("subscriber_opportunity", "Subscribers × monthly ARPU × 12", ("subscribers", "monthly_arpu"), lambda v: v["subscribers"] * monthly(v), "Annualized recurring revenue capacity."),
            ],
            "software_ai": [
                FormulaDefinition("seat_opportunity", "Customers × seats × ARPU", ("customers", "seats", "arpu"), lambda v: v["customers"] * v["seats"] * v["arpu"], "Seat-based revenue capacity."),
                FormulaDefinition("arr_opportunity", "ARR × retention", ("arr", "retention"), lambda v: v["arr"] * v["retention"], "ARR retention proxy; expansion must be added when sourced."),
            ],
            "capacity_infrastructure": [
                FormulaDefinition("capacity_opportunity", "Capacity × utilization × price", ("capacity_units", "utilization", "price_per_unit"), lambda v: v["capacity_units"] * v["utilization"] * v["price_per_unit"], "Capacity monetization proxy."),
            ],
            "holding_asset_manager": [
                FormulaDefinition("asset_management_opportunity", "AUM × fee rate", ("aum", "fee_rate"), lambda v: v["aum"] * v["fee_rate"], "Fee-related revenue capacity."),
            ],
            "commodity": [
                FormulaDefinition("resource_opportunity", "Production × realized price", ("production_volume", "realized_price"), lambda v: v["production_volume"] * v["realized_price"], "Resource revenue capacity."),
            ],
        }
        return definitions.get(framework.key, [])
