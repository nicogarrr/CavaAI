"""Long-term fundamental modelling with explicit evidence and assumption lineage.

This service is intentionally conservative. It can calculate a forward model from
coherent annual facts, but it never fills missing company data with a plausible
number. Policy assumptions (scenario spreads, terminal growth, or a fallback tax
rate) are returned as policy inputs so callers can distinguish them from facts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from math import isfinite, sqrt
from statistics import median
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import Company, FinancialFact, MarketPrice, NewsEvent, Position, ThesisChange
from app.services.company_framework import CompanyFramework, resolve_company_framework
from app.services.fundamental_model_repository import FundamentalModelRepository
from app.services.market_opportunity_service import MarketOpportunityEngine
from app.valuation.dcf_fcff import DCFInputs, run_dcf
from app.valuation.engines.base import default_terminal_growth, default_wacc
from app.valuation.reverse_dcf import ReverseDCFInputs, solve_required_growth


MODEL_VERSION = "long-term-fundamental-model-v1"
ANNUAL_METRICS = (
    "revenue",
    "gross_profit",
    "operating_income",
    "ebitda",
    "net_income",
    "operating_cash_flow",
    "capital_expenditure",
    "free_cash_flow",
    "working_capital",
    "net_debt",
    "shares_diluted",
)
RATIO_METRICS = (
    "gross_margin",
    "operating_margin",
    "ebitda_margin",
    "net_margin",
    "fcf_margin",
    "effective_tax_rate",
)
@dataclass(frozen=True)
class Assumption:
    value: float | None
    unit: str
    source_type: str
    basis: str
    source_fact_ids: list[int]
    confidence: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "unit": self.unit,
            "source_type": self.source_type,
            "basis": self.basis,
            "source_fact_ids": self.source_fact_ids,
            "confidence": self.confidence,
        }


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if isfinite(parsed) else None


def _date_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _unique_ids(*facts: FinancialFact | None, ids: list[int] | None = None) -> list[int]:
    result = list(ids or [])
    for fact in facts:
        if fact is not None and fact.id not in result:
            result.append(fact.id)
    return result


def _fact_evidence(fact: FinancialFact | None) -> dict[str, Any] | None:
    if fact is None:
        return None
    return {
        "fact_id": fact.id,
        "metric": fact.metric,
        "period": fact.period,
        "fiscal_year": fact.fiscal_year,
        "document_id": fact.source_id,
        "source_type": fact.source_type,
        "confidence": _float(fact.confidence),
        "reported": bool(fact.is_reported),
        "adjusted": bool(fact.is_adjusted),
    }


def _fact_line(
    fact: FinancialFact | None,
    *,
    value: float | None = None,
    unit: str | None = None,
    calculation: str | None = None,
    source_fact_ids: list[int] | None = None,
) -> dict[str, Any]:
    if fact is None and value is None:
        return {
            "value": None,
            "unit": unit or "unknown",
            "status": "insufficient_data",
            "source_fact_ids": source_fact_ids or [],
            "calculation": calculation,
            "evidence": [],
        }
    evidence = [_fact_evidence(fact)] if fact is not None else []
    return {
        "value": value if value is not None else _float(fact.value),
        "unit": unit or (fact.unit if fact is not None else "unknown"),
        "status": "reported" if fact is not None and fact.is_reported else "calculated",
        "source_fact_ids": _unique_ids(fact, ids=source_fact_ids),
        "calculation": calculation,
        "evidence": [item for item in evidence if item is not None],
    }


def _calculated_line(
    value: float | None,
    *,
    unit: str,
    source_fact_ids: list[int],
    calculation: str,
    basis: str,
) -> dict[str, Any]:
    return {
        "value": value,
        "unit": unit,
        "status": "calculated" if value is not None else "insufficient_data",
        "source_fact_ids": source_fact_ids,
        "calculation": calculation,
        "basis": basis,
        "evidence": [],
    }


def _is_annual(fact: FinancialFact) -> bool:
    quarter = (fact.fiscal_quarter or "").upper()
    period = (fact.period or "").upper()
    return not quarter.startswith("Q") and not period.startswith("Q")


class LongTermModelService:
    """Build the evidence-aware long-term model for one company."""

    def build(self, db: Session, company: Company, horizon: int = 5) -> dict[str, Any]:
        horizon = max(5, min(10, int(horizon)))
        framework = resolve_company_framework(company)
        market_metrics = MarketOpportunityEngine.metrics_for_framework(framework)
        driver_metrics = {
            self._metric_key(metric)
            for metric in framework.revenue_drivers + framework.kpis + framework.required_fact_metrics
        }
        fact_cache = {
            metric: self._facts(db, company, metric)
            for metric in set(ANNUAL_METRICS)
            | market_metrics
            | driver_metrics
            | {
                "depreciation_and_amortization",
                "maintenance_capex",
                "change_in_working_capital",
                "normalized_change_in_working_capital",
                "common_stock_repurchased",
                "dividends_paid",
                "total_debt",
                "ebitda",
                "total_equity",
                "cash_and_equivalents",
                "income_tax_expense",
                "income_before_tax",
            }
        }
        revenue_history = self._annual_by_year(fact_cache["revenue"])
        years = sorted(revenue_history)
        latest_year = years[-1] if years else None
        history = self._history_rows(fact_cache, years)

        current_price = self._current_price(db, company.id)
        current = history[-1] if history else {
            "period": None,
            "fiscal_year": None,
            "metrics": {},
        }

        assumptions, assumption_meta = self._assumptions(
            fact_cache=fact_cache,
            revenue_history=revenue_history,
            years=years,
            company=company,
        )
        driver_model = self._driver_model(framework, fact_cache)
        missing_mandatory_drivers = [
            driver["key"]
            for driver in driver_model
            if driver["required"] and driver["status"] == "missing"
        ]
        missing_core = [
            name
            for name, value in (
                ("revenue_history_two_periods", assumptions["revenue_growth"].value),
                ("normalized_fcf_margin", assumptions["fcf_margin"].value),
                ("shares_diluted", self._value_for_year(fact_cache["shares_diluted"], latest_year)),
            )
            if value is None
        ]

        scenarios: dict[str, Any] = {}
        scenario_specs: list[tuple[str, dict[str, Any]]] = []
        if not missing_core and latest_year is not None:
            scenario_specs = self._scenario_specs(
                assumptions,
                framework=framework,
                missing_mandatory_drivers=missing_mandatory_drivers,
            )
            for name, spec in scenario_specs:
                forecast = self._forecast(
                    fact_cache=fact_cache,
                    years=years,
                    latest_year=latest_year,
                    horizon=horizon,
                    scenario=name,
                    growth=spec["growth"],
                    fcf_margin=spec["fcf_margin"],
                    wacc=spec["wacc"],
                    assumptions=assumptions,
                )
                scenarios[name] = self._scenario_payload(
                    name=name,
                    spec=spec,
                    forecast=forecast,
                    assumptions=assumptions,
                    fact_cache=fact_cache,
                    latest_year=latest_year,
                )

        reverse_dcf = self._reverse_dcf(
            current_price=current_price,
            assumptions=assumptions,
            fact_cache=fact_cache,
            horizon=horizon,
            source_year=latest_year,
        )

        market_opportunity = MarketOpportunityEngine().build(
            db,
            company,
            framework,
            fact_cache=fact_cache,
            revenue_history=revenue_history,
            base_scenario=scenarios.get("base"),
            reverse_dcf=reverse_dcf,
            horizon=horizon,
        )

        revenue_ceiling = self._market_revenue_ceiling(market_opportunity)
        latest_revenue = self._value_for_year(fact_cache["revenue"], latest_year)
        if scenarios and revenue_ceiling and latest_revenue and latest_year is not None:
            constrained_specs = self._constrain_scenario_growth(
                scenario_specs,
                latest_revenue=latest_revenue,
                revenue_ceiling=revenue_ceiling,
                horizon=horizon,
            )
            if constrained_specs != scenario_specs:
                scenarios = {}
                for name, spec in constrained_specs:
                    forecast = self._forecast(
                        fact_cache=fact_cache,
                        years=years,
                        latest_year=latest_year,
                        horizon=horizon,
                        scenario=name,
                        growth=spec["growth"],
                        fcf_margin=spec["fcf_margin"],
                        wacc=spec["wacc"],
                        assumptions=assumptions,
                    )
                    scenarios[name] = self._scenario_payload(
                        name=name,
                        spec=spec,
                        forecast=forecast,
                        assumptions=assumptions,
                        fact_cache=fact_cache,
                        latest_year=latest_year,
                    )
                market_opportunity = MarketOpportunityEngine().build(
                    db,
                    company,
                    framework,
                    fact_cache=fact_cache,
                    revenue_history=revenue_history,
                    base_scenario=scenarios.get("base"),
                    reverse_dcf=reverse_dcf,
                    horizon=horizon,
                )
                market_opportunity["model_constraint"] = {
                    "applied": True,
                    "revenue_ceiling": revenue_ceiling,
                    "source": "minimum sourced future market or bottom-up capacity",
                }

        coverage = self._coverage(history, assumptions, scenarios)
        status = "ok" if not missing_core else "insufficient_data"
        if not missing_core and missing_mandatory_drivers:
            status = "missing_mandatory_drivers"
        limitations = self._limitations(
            fact_cache=fact_cache,
            years=years,
            missing_core=missing_core,
            market_opportunity=market_opportunity,
        )

        payload = {
            "ticker": company.ticker,
            "company": company.name,
            "currency": company.currency,
            "status": status,
            "publishable": (
                status == "ok"
                and not missing_mandatory_drivers
                and coverage["coverage_percent"] >= 60
            ),
            "model": "long_term_fundamental_modeling_engine",
            "model_version": MODEL_VERSION,
            "framework": framework.as_dict(),
            "horizon_years": horizon,
            "as_of_period": current.get("period"),
            "current_price": current_price,
            "missing_inputs": missing_core + missing_mandatory_drivers,
            "missing_mandatory_drivers": missing_mandatory_drivers,
            "historical_review": {
                "years_covered": len(years),
                "first_year": years[0] if years else None,
                "last_year": latest_year,
                "rows": history,
                "source_rule": "Every reported line carries fact_id, document_id, period and source_type.",
            },
            "current_snapshot": current,
            "assumptions": {key: value.as_dict() for key, value in assumptions.items()},
            "assumption_summary": assumption_meta,
            "operating_model": {
                "revenue_drivers": list(framework.revenue_drivers),
                "kpis": list(framework.kpis),
                "unit_economics": list(framework.unit_economics),
                "segment_model": list(framework.segment_model),
                "binding_constraints": list(framework.binding_constraints),
                "active_modules": list(framework.active_modules),
            },
            "driver_model": driver_model,
            "scenarios": scenarios,
            "reverse_dcf": reverse_dcf,
            "market_opportunity": market_opportunity,
            # Compatibility projection for clients that still read the old
            # market_share field. New consumers should use market_opportunity.
            "market_share": {
                **market_opportunity["market_share"],
                "implied_future_market_share": market_opportunity["market_share"].get("base_future_market_share"),
                "deprecated_alias": "market_opportunity",
            },
            "management_capital_allocation": self._capital_allocation(
                fact_cache=fact_cache,
                revenue_history=revenue_history,
                years=years,
            ),
            "quality_of_growth": self._quality_of_growth(
                fact_cache=fact_cache,
                revenue_history=revenue_history,
                years=years,
            ),
            "owner_earnings": self._owner_earnings(fact_cache, latest_year),
            "capex_analysis": self._capex_analysis(fact_cache, latest_year),
            "timeline": self._timeline(db, company.id),
            "what_must_be_true": self._what_must_be_true(
                assumptions=assumptions,
                reverse_dcf=reverse_dcf,
                base_scenario=scenarios.get("base"),
                fact_cache=fact_cache,
                latest_year=latest_year,
                market_opportunity=market_opportunity,
            ),
            "source_coverage": coverage,
            "limitations": limitations,
            "trace": {
                "engine": "long_term_fundamental_modeling",
                "model_version": MODEL_VERSION,
                "input_source": "financial_facts" if history else "insufficient_data",
                "fact_count": sum(len(items) for items in fact_cache.values()),
                "annual_periods": years,
            },
        }
        persisted = FundamentalModelRepository().persist(db, company, payload)
        payload["persistence"] = {
            "model_version_id": persisted.id if persisted else None,
            "version": persisted.version if persisted else None,
            "input_fingerprint": persisted.input_fingerprint if persisted else None,
            "status": "persisted" if persisted else "tenant_context_required",
        }
        return payload

    @staticmethod
    def _metric_key(metric: str) -> str:
        return (
            metric.strip()
            .lower()
            .replace("&", "and")
            .replace("/", "_")
            .replace("-", "_")
            .replace(" ", "_")
        )

    def _driver_model(
        self,
        framework: CompanyFramework,
        fact_cache: dict[str, list[FinancialFact]],
    ) -> list[dict[str, Any]]:
        revenue_keys = [self._metric_key(item) for item in framework.revenue_drivers]
        kpi_keys = [self._metric_key(item) for item in framework.kpis]
        required_keys = {self._metric_key(item) for item in framework.required_fact_metrics}
        ordered_keys = list(dict.fromkeys(revenue_keys + kpi_keys))
        drivers: list[dict[str, Any]] = []
        for key in ordered_keys:
            facts = fact_cache.get(key) or []
            fact = facts[-1] if facts else None
            drivers.append(
                {
                    "key": key,
                    "driver_type": "revenue_driver" if key in revenue_keys else "kpi",
                    "required": key in required_keys,
                    "status": "sourced" if fact else "missing",
                    "value": _float(fact.value) if fact else None,
                    "unit": fact.unit if fact else "unknown",
                    "confidence": _float(fact.confidence) if fact else 0.0,
                    "source_fact_ids": [fact.id] if fact else [],
                    "trace": {
                        "period": fact.period if fact else None,
                        "fiscal_year": fact.fiscal_year if fact else None,
                        "source_type": fact.source_type if fact else None,
                    },
                }
            )
        return drivers

    @staticmethod
    def _market_revenue_ceiling(market_opportunity: dict[str, Any]) -> float | None:
        candidates = [
            _float((market_opportunity.get("top_down") or {}).get("future_market", {}).get("value")),
            _float((market_opportunity.get("bottom_up") or {}).get("value")),
        ]
        positive = [value for value in candidates if value is not None and value > 0]
        return min(positive) if positive else None

    @staticmethod
    def _constrain_scenario_growth(
        specs: list[tuple[str, dict[str, Any]]],
        *,
        latest_revenue: float,
        revenue_ceiling: float,
        horizon: int,
    ) -> list[tuple[str, dict[str, Any]]]:
        if latest_revenue <= 0 or revenue_ceiling <= latest_revenue:
            maximum_growth = 0.0
        else:
            maximum_growth = (revenue_ceiling / latest_revenue) ** (1 / horizon) - 1
        constrained: list[tuple[str, dict[str, Any]]] = []
        for name, original in specs:
            spec = dict(original)
            if spec["growth"] > maximum_growth:
                spec["growth"] = maximum_growth
                spec["drivers"] = list(spec["drivers"]) + ["market_opportunity_revenue_ceiling"]
                spec["market_constraint"] = {
                    "revenue_ceiling": revenue_ceiling,
                    "maximum_cagr": maximum_growth,
                }
            constrained.append((name, spec))
        return constrained

    def _facts(self, db: Session, company: Company, metric: str) -> list[FinancialFact]:
        return list(
            db.scalars(
                select(FinancialFact)
                .where(FinancialFact.company_id == company.id, FinancialFact.metric == metric)
                .order_by(FinancialFact.fiscal_year.asc().nullslast(), FinancialFact.created_at.asc())
                .limit(200)
            ).all()
        )

    def _annual_by_year(self, facts: list[FinancialFact]) -> dict[int, FinancialFact]:
        result: dict[int, FinancialFact] = {}
        for fact in facts:
            if fact.fiscal_year is None or not _is_annual(fact):
                continue
            # Facts are ordered oldest-to-newest. Keeping the last one prefers the
            # most recently ingested source if a period exists twice.
            result[int(fact.fiscal_year)] = fact
        return result

    def _value_for_year(self, facts: list[FinancialFact], year: int | None) -> float | None:
        if year is None:
            return None
        fact = self._annual_by_year(facts).get(year)
        return _float(fact.value) if fact else None

    def _fact_for_year(self, facts: list[FinancialFact], year: int | None) -> FinancialFact | None:
        if year is None:
            return None
        return self._annual_by_year(facts).get(year)

    def _history_rows(self, fact_cache: dict[str, list[FinancialFact]], years: list[int]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for year in years[-10:]:
            revenue_fact = self._fact_for_year(fact_cache["revenue"], year)
            period = revenue_fact.period if revenue_fact else f"FY{year}"
            metrics: dict[str, Any] = {}
            for metric in ANNUAL_METRICS:
                fact = self._fact_for_year(fact_cache[metric], year)
                if metric == "free_cash_flow" and fact is None:
                    ocf = self._fact_for_year(fact_cache["operating_cash_flow"], year)
                    capex = self._fact_for_year(fact_cache["capital_expenditure"], year)
                    if ocf and capex:
                        value = (_float(ocf.value) or 0) + (_float(capex.value) or 0)
                        metrics[metric] = _calculated_line(
                            value,
                            unit="USD",
                            source_fact_ids=_unique_ids(ocf, capex),
                            calculation="operating_cash_flow + capital_expenditure",
                            basis="derived because reported free_cash_flow is missing",
                        )
                        continue
                metrics[metric] = _fact_line(fact)

            revenue = metrics["revenue"]["value"]
            for metric, numerator in (
                ("gross_margin", "gross_profit"),
                ("operating_margin", "operating_income"),
                ("ebitda_margin", "ebitda"),
                ("net_margin", "net_income"),
                ("fcf_margin", "free_cash_flow"),
            ):
                numerator_line = metrics[numerator]
                ids = _unique_ids(ids=metrics["revenue"]["source_fact_ids"] + numerator_line["source_fact_ids"])
                value = (
                    numerator_line["value"] / revenue
                    if revenue not in (None, 0) and numerator_line["value"] is not None
                    else None
                )
                metrics[metric] = _calculated_line(
                    value,
                    unit="decimal",
                    source_fact_ids=ids,
                    calculation=f"{numerator} / revenue",
                    basis="same fiscal year",
                )
            rows.append({"period": period, "fiscal_year": year, "metrics": metrics})
        return rows

    def _series(
        self,
        fact_cache: dict[str, list[FinancialFact]],
        metric: str,
        years: list[int],
    ) -> list[dict[str, Any]]:
        series: list[dict[str, Any]] = []
        for year in years:
            fact = self._fact_for_year(fact_cache[metric], year)
            if fact is not None:
                series.append({"year": year, "value": _float(fact.value), "fact_ids": [fact.id]})
        return series

    def _derived_fcf_series(
        self,
        fact_cache: dict[str, list[FinancialFact]],
        years: list[int],
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for year in years:
            fcf = self._fact_for_year(fact_cache["free_cash_flow"], year)
            if fcf:
                result.append({"year": year, "value": _float(fcf.value), "fact_ids": [fcf.id]})
                continue
            ocf = self._fact_for_year(fact_cache["operating_cash_flow"], year)
            capex = self._fact_for_year(fact_cache["capital_expenditure"], year)
            if ocf and capex:
                result.append(
                    {
                        "year": year,
                        "value": (_float(ocf.value) or 0) + (_float(capex.value) or 0),
                        "fact_ids": _unique_ids(ocf, capex),
                    }
                )
        return result

    def _assumptions(
        self,
        *,
        fact_cache: dict[str, list[FinancialFact]],
        revenue_history: dict[int, FinancialFact],
        years: list[int],
        company: Company,
    ) -> tuple[dict[str, Assumption], dict[str, Any]]:
        revenue_series = [
            {"year": year, "value": _float(fact.value), "fact_ids": [fact.id]}
            for year, fact in sorted(revenue_history.items())
            if _float(fact.value) is not None and _float(fact.value) > 0
        ]
        growth_values: list[float] = []
        growth_ids: list[int] = []
        for previous, current in zip(revenue_series, revenue_series[1:]):
            if previous["value"] and current["value"] is not None:
                growth_values.append(current["value"] / previous["value"] - 1)
                growth_ids.extend(previous["fact_ids"] + current["fact_ids"])
        growth = None
        if len(revenue_series) >= 2:
            first = revenue_series[0]
            last = revenue_series[-1]
            span = max(1, last["year"] - first["year"])
            growth = (last["value"] / first["value"]) ** (1 / span) - 1
            growth_ids = _unique_ids(ids=first["fact_ids"] + last["fact_ids"])

        fcf_series = self._derived_fcf_series(fact_cache, years)
        revenue_by_year = {item["year"]: item for item in revenue_series}
        margin_points = [
            item
            for item in fcf_series
            if item["year"] in revenue_by_year and revenue_by_year[item["year"]]["value"]
        ]
        margin_values = [item["value"] / revenue_by_year[item["year"]]["value"] for item in margin_points]
        margin_ids: list[int] = []
        for item in margin_points[-5:]:
            margin_ids.extend(item["fact_ids"] + revenue_by_year[item["year"]]["fact_ids"])
        fcf_margin = median(margin_values[-5:]) if margin_values else None

        def ratio_assumption(metric: str, numerator: str, denominator: str) -> Assumption:
            points: list[tuple[float, list[int]]] = []
            numerator_series = self._derived_fcf_series(fact_cache, years) if numerator == "free_cash_flow" else self._series(fact_cache, numerator, years)
            denominator_series = self._series(fact_cache, denominator, years)
            denominator_by_year = {item["year"]: item for item in denominator_series}
            for item in numerator_series:
                denominator_item = denominator_by_year.get(item["year"])
                if denominator_item and denominator_item["value"] not in (None, 0):
                    points.append((item["value"] / denominator_item["value"], item["fact_ids"] + denominator_item["fact_ids"]))
            values = [value for value, _ in points]
            ids = [fact_id for _, point_ids in points[-5:] for fact_id in point_ids]
            return Assumption(
                value=median(values[-5:]) if values else None,
                unit="decimal",
                source_type="financial_facts" if values else "missing",
                basis=f"median of latest {min(5, len(values))} annual {metric} observations",
                source_fact_ids=_unique_ids(ids=ids),
                confidence=self._confidence(fact_cache, ids),
            )

        gross_margin = ratio_assumption("gross_margin", "gross_profit", "revenue")
        operating_margin = ratio_assumption("operating_margin", "operating_income", "revenue")
        ebitda_margin = ratio_assumption("ebitda_margin", "ebitda", "revenue")
        net_margin = ratio_assumption("net_margin", "net_income", "revenue")

        tax_rate = ratio_assumption("effective_tax_rate", "income_tax_expense", "income_before_tax")
        if tax_rate.value is not None:
            tax_rate = Assumption(
                value=max(0, min(tax_rate.value, 0.60)),
                unit="decimal",
                source_type=tax_rate.source_type,
                basis=tax_rate.basis,
                source_fact_ids=tax_rate.source_fact_ids,
                confidence=tax_rate.confidence,
            )
        else:
            tax_rate = Assumption(
                value=0.25,
                unit="decimal",
                source_type="model_policy",
                basis="fallback statutory tax rate; replace with reported tax data",
                source_fact_ids=[],
                confidence=0.35,
            )

        shares_series = self._series(fact_cache, "shares_diluted", years)
        shares_cagr = self._cagr(shares_series)
        shares_ids = [fact_id for item in shares_series for fact_id in item["fact_ids"]]
        # WACC is a market assumption in the current product. Keep its policy
        # origin explicit until risk-free-rate/beta facts are fully source-tagged.
        wacc = Assumption(
            value=default_wacc(company),
            unit="decimal",
            source_type="model_policy",
            basis="company valuation policy; replace with source-tagged WACC inputs",
            source_fact_ids=[],
            confidence=0.40,
        )
        terminal = Assumption(
            value=default_terminal_growth(company),
            unit="decimal",
            source_type="model_policy",
            basis="terminal growth policy from company framework",
            source_fact_ids=[],
            confidence=0.40,
        )

        capex_intensity = ratio_assumption("capex_to_revenue", "capital_expenditure", "revenue")
        if capex_intensity.value is not None:
            capex_intensity = Assumption(
                value=abs(capex_intensity.value),
                unit="decimal",
                source_type=capex_intensity.source_type,
                basis="median absolute capital expenditure / revenue",
                source_fact_ids=capex_intensity.source_fact_ids,
                confidence=capex_intensity.confidence,
            )

        working_capital = ratio_assumption("working_capital_to_revenue", "working_capital", "revenue")
        assumptions = {
            "revenue_growth": Assumption(growth, "decimal", "financial_facts" if growth is not None else "missing", "annual revenue CAGR across available history", growth_ids, self._confidence(fact_cache, growth_ids)),
            "fcf_margin": Assumption(fcf_margin, "decimal", "financial_facts" if fcf_margin is not None else "missing", "median of latest annual FCF margins", _unique_ids(ids=margin_ids), self._confidence(fact_cache, margin_ids)),
            "gross_margin": gross_margin,
            "operating_margin": operating_margin,
            "ebitda_margin": ebitda_margin,
            "net_margin": net_margin,
            "effective_tax_rate": tax_rate,
            "capex_to_revenue": capex_intensity,
            "working_capital_to_revenue": working_capital,
            "shares_cagr": Assumption(shares_cagr, "decimal", "financial_facts" if shares_cagr is not None else "missing", "diluted share count CAGR across available history", _unique_ids(ids=shares_ids), self._confidence(fact_cache, shares_ids)),
            "wacc": wacc,
            "terminal_growth": terminal,
        }
        growth_spread = self._spread(growth_values)
        margin_spread = self._spread(margin_values)
        assumption_meta = {
            "growth_observations": growth_values,
            "growth_spread_policy": max(0.02, min(0.08, growth_spread * 0.75 if growth_values else 0.02)),
            "margin_spread_policy": max(0.02, min(0.06, margin_spread * 0.75 if margin_values else 0.02)),
            "normalization_window_years": min(5, len(years)),
            "share_count_observations": len(shares_series),
        }
        return assumptions, assumption_meta

    def _confidence(self, fact_cache: dict[str, list[FinancialFact]], fact_ids: list[int]) -> float:
        if not fact_ids:
            return 0.0
        by_id = {fact.id: fact for facts in fact_cache.values() for fact in facts}
        values = [_float(by_id[fact_id].confidence) for fact_id in fact_ids if fact_id in by_id]
        return min(values) if values else 0.0

    @staticmethod
    def _cagr(series: list[dict[str, Any]]) -> float | None:
        if len(series) < 2:
            return None
        first, last = series[0], series[-1]
        if first["value"] in (None, 0) or last["value"] is None or first["year"] == last["year"]:
            return None
        if first["value"] < 0 or last["value"] < 0:
            return None
        return (last["value"] / first["value"]) ** (1 / (last["year"] - first["year"])) - 1

    @staticmethod
    def _spread(values: list[float]) -> float:
        if len(values) < 2:
            return 0.0
        average = sum(values) / len(values)
        variance = sum((value - average) ** 2 for value in values) / len(values)
        return sqrt(max(0.0, variance))

    def _scenario_specs(
        self,
        assumptions: dict[str, Assumption],
        *,
        framework: CompanyFramework,
        missing_mandatory_drivers: list[str],
    ) -> list[tuple[str, dict[str, Any]]]:
        growth = assumptions["revenue_growth"].value
        margin = assumptions["fcf_margin"].value
        wacc = assumptions["wacc"].value
        terminal = assumptions["terminal_growth"].value
        assert growth is not None and margin is not None and wacc is not None and terminal is not None
        growth_spread = max(0.02, min(0.08, abs(growth) * 0.35))
        margin_spread = max(0.02, min(0.06, abs(margin) * 0.25))
        confidence_values = [
            assumption.confidence
            for assumption in assumptions.values()
            if assumption.value is not None
        ]
        evidence_confidence = (
            sum(confidence_values) / len(confidence_values)
            if confidence_values
            else 0.0
        )
        base_probability = max(0.38, min(0.68, 0.38 + evidence_confidence * 0.30))
        remaining = 1.0 - base_probability
        upside_share = max(0.35, min(0.65, 0.50 + growth * 0.75))
        if missing_mandatory_drivers:
            base_probability = max(0.34, base_probability - 0.10)
            remaining = 1.0 - base_probability
            upside_share = min(upside_share, 0.40)
        bull_probability = remaining * upside_share
        bear_probability = remaining - bull_probability
        probability_basis = {
            "method": "company_evidence_confidence_and_growth_skew",
            "evidence_confidence": evidence_confidence,
            "historical_growth": growth,
            "framework": framework.key,
            "missing_mandatory_driver_count": len(missing_mandatory_drivers),
        }
        framework_drivers = list(framework.revenue_drivers[:3])
        return [
            ("bear", {"probability": bear_probability, "probability_basis": probability_basis, "growth": max(growth - growth_spread, -0.25), "fcf_margin": max(margin - margin_spread, 0.0), "wacc": wacc + 0.02, "terminal_growth": max(terminal - 0.005, 0.0), "drivers": framework_drivers + ["execution_downside", "margin_compression", "higher_cost_of_capital"]}),
            ("base", {"probability": base_probability, "probability_basis": probability_basis, "growth": growth, "fcf_margin": margin, "wacc": wacc, "terminal_growth": terminal, "drivers": framework_drivers + ["historical_revenue_cagr", "normalized_fcf_margin"]}),
            ("bull", {"probability": bull_probability, "probability_basis": probability_basis, "growth": min(growth + growth_spread, 0.50), "fcf_margin": min(margin + margin_spread, 0.60), "wacc": max(wacc - 0.01, terminal + 0.01), "terminal_growth": terminal, "drivers": framework_drivers + ["execution_upside", "margin_expansion", "lower_cost_of_capital"]}),
        ]

    def _forecast(
        self,
        *,
        fact_cache: dict[str, list[FinancialFact]],
        years: list[int],
        latest_year: int,
        horizon: int,
        scenario: str,
        growth: float,
        fcf_margin: float,
        wacc: float,
        assumptions: dict[str, Assumption],
    ) -> list[dict[str, Any]]:
        latest_revenue = self._value_for_year(fact_cache["revenue"], latest_year)
        latest_shares = self._value_for_year(fact_cache["shares_diluted"], latest_year)
        latest_net_debt = self._value_for_year(fact_cache["net_debt"], latest_year)
        if latest_revenue is None or latest_shares in (None, 0):
            return []

        share_growth = assumptions["shares_cagr"].value or 0.0
        capex_ratio = assumptions["capex_to_revenue"].value
        working_capital_ratio = assumptions["working_capital_to_revenue"].value
        tax_rate = assumptions["effective_tax_rate"].value or 0.25
        base_ids = _unique_ids(ids=assumptions["revenue_growth"].source_fact_ids)
        margin_ids = _unique_ids(ids=assumptions["fcf_margin"].source_fact_ids)
        share_ids = _unique_ids(ids=assumptions["shares_cagr"].source_fact_ids)
        capex_ids = _unique_ids(ids=assumptions["capex_to_revenue"].source_fact_ids)
        tax_ids = _unique_ids(ids=assumptions["effective_tax_rate"].source_fact_ids)

        previous_revenue = latest_revenue
        previous_shares = latest_shares
        previous_working_capital = self._value_for_year(fact_cache["working_capital"], latest_year)
        latest_fcf = self._derived_fcf_value(fact_cache, latest_year)
        latest_margin = latest_fcf / latest_revenue if latest_fcf is not None and latest_revenue else fcf_margin
        forecasts: list[dict[str, Any]] = []
        for offset in range(1, horizon + 1):
            year = latest_year + offset
            revenue = previous_revenue * (1 + growth)
            shares = max(0.000001, previous_shares * (1 + share_growth))
            fcf = revenue * fcf_margin
            capex = -revenue * capex_ratio if capex_ratio is not None else None
            operating_cash_flow = fcf - capex if capex is not None else None
            working_capital = revenue * working_capital_ratio if working_capital_ratio is not None else None
            working_capital_absorption = (
                working_capital - (previous_working_capital if previous_working_capital is not None else working_capital)
                if working_capital is not None
                else None
            )
            gross_profit = revenue * assumptions["gross_margin"].value if assumptions["gross_margin"].value is not None else None
            operating_income = revenue * assumptions["operating_margin"].value if assumptions["operating_margin"].value is not None else None
            ebitda = revenue * assumptions["ebitda_margin"].value if assumptions["ebitda_margin"].value is not None else None
            net_income = revenue * assumptions["net_margin"].value if assumptions["net_margin"].value is not None else (
                operating_income * (1 - tax_rate) if operating_income is not None else None
            )
            roic = self._forward_roic(db=None, company=None, operating_income=operating_income, tax_rate=tax_rate, fact_cache=fact_cache, latest_year=latest_year)
            point_ids = _unique_ids(ids=base_ids + margin_ids)
            evidence = {
                "revenue": {"source_fact_ids": base_ids, "calculation": "prior revenue * (1 + scenario revenue growth)"},
                "gross_profit": {"source_fact_ids": point_ids + assumptions["gross_margin"].source_fact_ids, "calculation": "revenue * historical gross margin"},
                "operating_income": {"source_fact_ids": point_ids + assumptions["operating_margin"].source_fact_ids, "calculation": "revenue * historical operating margin"},
                "ebitda": {"source_fact_ids": point_ids + assumptions["ebitda_margin"].source_fact_ids, "calculation": "revenue * historical EBITDA margin"},
                "net_income": {"source_fact_ids": point_ids + assumptions["net_margin"].source_fact_ids + tax_ids, "calculation": "revenue * historical net margin or NOPAT proxy"},
                "operating_cash_flow": {"source_fact_ids": point_ids + capex_ids, "calculation": "FCF - capital expenditure"},
                "capital_expenditure": {"source_fact_ids": capex_ids, "calculation": "-revenue * historical capex intensity"},
                "free_cash_flow": {"source_fact_ids": point_ids, "calculation": "revenue * scenario FCF margin"},
                "working_capital": {"source_fact_ids": assumptions["working_capital_to_revenue"].source_fact_ids, "calculation": "revenue * historical working capital / revenue"},
                "net_debt": {"source_fact_ids": [self._fact_for_year(fact_cache["net_debt"], latest_year).id] if self._fact_for_year(fact_cache["net_debt"], latest_year) else [], "calculation": "held flat; debt paydown/capital allocation not modelled"},
                "shares_diluted": {"source_fact_ids": share_ids, "calculation": "prior shares * (1 + historical share-count CAGR)"},
                "fcf_per_share": {"source_fact_ids": point_ids + share_ids, "calculation": "free cash flow / diluted shares"},
                "roic": {"source_fact_ids": point_ids + tax_ids + self._balance_fact_ids(fact_cache, latest_year), "calculation": "NOPAT / current invested capital proxy"},
            }
            forecasts.append(
                {
                    "year": year,
                    "revenue": revenue,
                    "gross_profit": gross_profit,
                    "operating_income": operating_income,
                    "ebitda": ebitda,
                    "net_income": net_income,
                    "operating_cash_flow": operating_cash_flow,
                    "capital_expenditure": capex,
                    "free_cash_flow": fcf,
                    "working_capital": working_capital,
                    "working_capital_absorption": working_capital_absorption,
                    "net_debt": latest_net_debt,
                    "shares_diluted": shares,
                    "fcf_per_share": fcf / shares,
                    "fcf_margin": fcf / revenue if revenue else None,
                    "roic": roic,
                    "evidence": evidence,
                    "scenario": scenario,
                    "wacc": wacc,
                }
            )
            previous_revenue = revenue
            previous_shares = shares
            previous_working_capital = working_capital
        return forecasts

    def _forward_roic(
        self,
        *,
        db: Session | None,
        company: Company | None,
        operating_income: float | None,
        tax_rate: float,
        fact_cache: dict[str, list[FinancialFact]],
        latest_year: int,
    ) -> float | None:
        if operating_income is None:
            return None
        debt = self._value_for_year(fact_cache["total_debt"], latest_year)
        equity = self._value_for_year(fact_cache["total_equity"], latest_year)
        cash = self._value_for_year(fact_cache["cash_and_equivalents"], latest_year)
        if debt is None or equity is None or cash is None:
            return None
        invested_capital = debt + equity - cash
        if invested_capital <= 0:
            return None
        return operating_income * (1 - tax_rate) / invested_capital

    def _balance_fact_ids(self, fact_cache: dict[str, list[FinancialFact]], year: int) -> list[int]:
        return _unique_ids(
            self._fact_for_year(fact_cache["total_debt"], year),
            self._fact_for_year(fact_cache["total_equity"], year),
            self._fact_for_year(fact_cache["cash_and_equivalents"], year),
        )

    def _derived_fcf_value(self, fact_cache: dict[str, list[FinancialFact]], year: int) -> float | None:
        fact = self._fact_for_year(fact_cache["free_cash_flow"], year)
        if fact:
            return _float(fact.value)
        ocf = self._fact_for_year(fact_cache["operating_cash_flow"], year)
        capex = self._fact_for_year(fact_cache["capital_expenditure"], year)
        if ocf and capex:
            return (_float(ocf.value) or 0) + (_float(capex.value) or 0)
        return None

    def _scenario_payload(
        self,
        *,
        name: str,
        spec: dict[str, Any],
        forecast: list[dict[str, Any]],
        assumptions: dict[str, Assumption],
        fact_cache: dict[str, list[FinancialFact]],
        latest_year: int,
    ) -> dict[str, Any]:
        latest_revenue = self._value_for_year(fact_cache["revenue"], latest_year)
        latest_shares = self._value_for_year(fact_cache["shares_diluted"], latest_year)
        net_debt = self._value_for_year(fact_cache["net_debt"], latest_year) or 0.0
        dcf = None
        if latest_revenue is not None and latest_shares:
            dcf_result = run_dcf(
                DCFInputs(
                    revenue=latest_revenue,
                    revenue_growth=spec["growth"],
                    fcf_margin=spec["fcf_margin"],
                    wacc=spec["wacc"],
                    terminal_growth=spec["terminal_growth"],
                    net_debt=net_debt,
                    shares_outstanding=latest_shares,
                    years=len(forecast),
                )
            )
            dcf = {
                "enterprise_value": dcf_result.enterprise_value,
                "equity_value": dcf_result.equity_value,
                "value_per_share": dcf_result.value_per_share,
                "trace": dcf_result.trace,
            }
        first = forecast[0] if forecast else None
        return {
            "probability": spec["probability"],
            "probability_basis": spec.get("probability_basis", {}),
            "assumptions": {
                "revenue_growth": {
                    "value": spec["growth"],
                    "unit": "decimal",
                    "source_type": "model_policy_plus_history",
                    "basis": "base historical CAGR adjusted by explicit scenario spread",
                    "source_fact_ids": assumptions["revenue_growth"].source_fact_ids,
                },
                "fcf_margin": {
                    "value": spec["fcf_margin"],
                    "unit": "decimal",
                    "source_type": "model_policy_plus_history",
                    "basis": "normalized historical FCF margin adjusted by explicit scenario spread",
                    "source_fact_ids": assumptions["fcf_margin"].source_fact_ids,
                },
                "wacc": {"value": spec["wacc"], "unit": "decimal", "source_type": "model_policy", "basis": "company WACC policy with scenario adjustment", "source_fact_ids": []},
                "terminal_growth": {"value": spec["terminal_growth"], "unit": "decimal", "source_type": "model_policy", "basis": "terminal growth policy with bear adjustment", "source_fact_ids": []},
            },
            "drivers": spec["drivers"],
            "forecast": forecast,
            "year_5": next((item for item in forecast if item["year"] == latest_year + 5), forecast[-1] if forecast else None),
            "terminal_year": forecast[-1] if forecast else None,
            "revenue_bridge": self._revenue_bridge(latest_year, first, latest_revenue),
            "fcf_bridge": self._fcf_bridge(fact_cache, latest_year, first),
            "valuation": dcf,
        }

    def _revenue_bridge(self, latest_year: int, first: dict[str, Any] | None, current_revenue: float | None) -> dict[str, Any]:
        if first is None or current_revenue is None:
            return {"status": "insufficient_data", "items": []}
        delta = first["revenue"] - current_revenue
        return {
            "status": "partial",
            "from_year": latest_year,
            "to_year": first["year"],
            "items": [
                {"label": "Revenue actual", "value": current_revenue, "source_fact_ids": first["evidence"]["revenue"]["source_fact_ids"]},
                {"label": "Crecimiento no atribuido", "value": delta, "source_fact_ids": first["evidence"]["revenue"]["source_fact_ids"], "note": "Pricing, volumen, mix, FX y M&A requieren drivers sectoriales o de segmento."},
                {"label": "Revenue modelado", "value": first["revenue"], "source_fact_ids": first["evidence"]["revenue"]["source_fact_ids"]},
            ],
            "unavailable_drivers": ["price", "volume", "mix", "fx", "m_and_a", "churn"],
        }

    def _fcf_bridge(self, fact_cache: dict[str, list[FinancialFact]], latest_year: int, first: dict[str, Any] | None) -> dict[str, Any]:
        current_revenue = self._value_for_year(fact_cache["revenue"], latest_year)
        current_fcf = self._derived_fcf_value(fact_cache, latest_year)
        if first is None or current_revenue is None or current_fcf is None:
            return {"status": "insufficient_data", "items": []}
        current_margin = current_fcf / current_revenue if current_revenue else 0
        revenue_effect = (first["revenue"] - current_revenue) * current_margin
        margin_effect = first["revenue"] * ((first["fcf_margin"] or 0) - current_margin)
        return {
            "status": "partial",
            "from_year": latest_year,
            "to_year": first["year"],
            "items": [
                {"label": "FCF actual", "value": current_fcf, "source_fact_ids": first["evidence"]["free_cash_flow"]["source_fact_ids"]},
                {"label": "Escala de revenue", "value": revenue_effect, "source_fact_ids": first["evidence"]["revenue"]["source_fact_ids"]},
                {"label": "Cambio de margen FCF", "value": margin_effect, "source_fact_ids": first["evidence"]["free_cash_flow"]["source_fact_ids"]},
                {"label": "FCF modelado", "value": first["free_cash_flow"], "source_fact_ids": first["evidence"]["free_cash_flow"]["source_fact_ids"]},
            ],
            "unavailable_drivers": ["working_capital", "taxes_separately", "maintenance_capex", "growth_capex"],
        }

    def _reverse_dcf(
        self,
        *,
        current_price: float | None,
        assumptions: dict[str, Assumption],
        fact_cache: dict[str, list[FinancialFact]],
        horizon: int,
        source_year: int | None,
    ) -> dict[str, Any]:
        revenue = self._value_for_year(fact_cache["revenue"], source_year)
        shares = self._value_for_year(fact_cache["shares_diluted"], source_year)
        margin = assumptions["fcf_margin"].value
        wacc = assumptions["wacc"].value
        terminal = assumptions["terminal_growth"].value
        if current_price is None or revenue is None or shares in (None, 0) or margin is None or wacc is None or terminal is None:
            return {"status": "insufficient_data", "market_price": current_price, "missing_inputs": ["market_price", "revenue", "fcf_margin", "shares_diluted"], "trace": {"method": "binary_search_reverse_dcf", "source_fact_ids": assumptions["fcf_margin"].source_fact_ids}}
        net_debt = self._value_for_year(fact_cache["net_debt"], source_year) or 0.0
        solved = solve_required_growth(
            ReverseDCFInputs(
                market_price=current_price,
                revenue=revenue,
                fcf_margin=margin,
                wacc=wacc,
                terminal_growth=terminal,
                net_debt=net_debt,
                shares_outstanding=shares,
                years=horizon,
            )
        )
        return {
            "status": "ok",
            **solved,
            "base_revenue_growth": assumptions["revenue_growth"].value,
            "growth_gap_vs_base": solved["required_revenue_growth"] - (assumptions["revenue_growth"].value or 0),
            "source_fact_ids": _unique_ids(ids=assumptions["revenue_growth"].source_fact_ids + assumptions["fcf_margin"].source_fact_ids),
            "trace": {**solved["trace"], "source_fact_ids": assumptions["revenue_growth"].source_fact_ids + assumptions["fcf_margin"].source_fact_ids, "horizon_years": horizon},
        }

    def _capital_allocation(
        self,
        *,
        fact_cache: dict[str, list[FinancialFact]],
        revenue_history: dict[int, FinancialFact],
        years: list[int],
    ) -> dict[str, Any]:
        metrics: dict[str, Any] = {}
        shares = self._series(fact_cache, "shares_diluted", years)
        metrics["share_count_cagr"] = self._metric_value(self._cagr(shares), "decimal", [fact_id for item in shares for fact_id in item["fact_ids"]], "diluted shares CAGR")
        for metric, label in (("common_stock_repurchased", "buyback_to_revenue"), ("dividends_paid", "dividend_to_revenue")):
            values: list[float] = []
            ids: list[int] = []
            for year, revenue_fact in revenue_history.items():
                action_fact = self._fact_for_year(fact_cache[metric], year)
                revenue = _float(revenue_fact.value)
                action = _float(action_fact.value) if action_fact else None
                if revenue and action is not None:
                    values.append(abs(action) / revenue)
                    ids.extend([revenue_fact.id, action_fact.id])
            metrics[label] = self._metric_value(median(values[-5:]) if values else None, "decimal", _unique_ids(ids=ids), f"median {metric} / revenue")
        fcf = self._derived_fcf_series(fact_cache, years)
        net_income = self._series(fact_cache, "net_income", years)
        metrics["fcf_conversion"] = self._ratio_metric(fcf, net_income, "free_cash_flow / net_income")
        net_debt = self._series(fact_cache, "net_debt", years)
        ebitda = self._series(fact_cache, "ebitda", years)
        metrics["net_debt_to_ebitda"] = self._ratio_metric(net_debt, ebitda, "net_debt / ebitda")
        metrics["reinvestment_rate"] = {"value": None, "unit": "decimal", "status": "insufficient_data", "source_fact_ids": [], "note": "Requires maintenance capex and normalized working capital."}
        available = [item for item in metrics.values() if item.get("value") is not None]
        return {
            "status": "partial" if available else "insufficient_data",
            "metrics": metrics,
            "conclusion": "Review historical capital allocation against share count and FCF conversion; M&A ROI is not sourced yet.",
            "missing_inputs": ["m_and_a_purchase_price_and_post_deal_returns", "maintenance_capex", "normalized_working_capital"],
        }

    def _quality_of_growth(
        self,
        *,
        fact_cache: dict[str, list[FinancialFact]],
        revenue_history: dict[int, FinancialFact],
        years: list[int],
    ) -> dict[str, Any]:
        growth = self._cagr(self._series(fact_cache, "revenue", years))
        fcf = self._derived_fcf_series(fact_cache, years)
        revenue = self._series(fact_cache, "revenue", years)
        margin_by_year = {item["year"]: item["value"] / next(x["value"] for x in revenue if x["year"] == item["year"]) for item in fcf if next((x["value"] for x in revenue if x["year"] == item["year"]), None)}
        margin_change = None
        if len(margin_by_year) >= 2:
            margin_change = margin_by_year[max(margin_by_year)] - margin_by_year[min(margin_by_year)]
        shares_cagr = self._cagr(self._series(fact_cache, "shares_diluted", years))
        if growth is None:
            quality = "unknown"
        elif margin_change is not None and (shares_cagr is None or shares_cagr <= 0) and margin_change >= -0.01:
            quality = "high"
        elif margin_change is not None or shares_cagr is not None:
            quality = "medium"
        else:
            quality = "unknown"
        ids = [fact.id for fact in revenue_history.values()]
        return {
            "status": "ok" if growth is not None else "insufficient_data",
            "quality": quality,
            "revenue_cagr": self._metric_value(growth, "decimal", ids, "annual revenue CAGR"),
            "fcf_margin_change": self._metric_value(margin_change, "decimal", [fact_id for item in fcf for fact_id in item["fact_ids"]] + ids, "latest FCF margin minus earliest FCF margin"),
            "share_count_cagr": self._metric_value(shares_cagr, "decimal", self._fact_ids_for_metric(fact_cache["shares_diluted"]), "diluted share count CAGR"),
            "unavailable_drivers": ["pricing", "volume", "mix", "fx", "m_and_a", "cyclical_vs_structural"],
            "conclusion": "Growth quality is a partial assessment until price/volume/mix, M&A and working-capital drivers are sourced.",
        }

    def _owner_earnings(self, fact_cache: dict[str, list[FinancialFact]], year: int | None) -> dict[str, Any]:
        net_income = self._fact_for_year(fact_cache["net_income"], year)
        dna = self._fact_for_year(fact_cache["depreciation_and_amortization"], year)
        maintenance = self._fact_for_year(fact_cache["maintenance_capex"], year)
        wc = self._fact_for_year(fact_cache["normalized_change_in_working_capital"], year) or self._fact_for_year(fact_cache["change_in_working_capital"], year)
        missing = [label for label, fact in (("net_income", net_income), ("depreciation_and_amortization", dna), ("maintenance_capex", maintenance), ("normalized_working_capital", wc)) if fact is None]
        if missing:
            return {"status": "insufficient_data", "value": None, "formula": "net income + D&A - maintenance capex - normalized change in working capital", "missing_inputs": missing, "source_fact_ids": _unique_ids(net_income)}
        values = [_float(item.value) or 0 for item in (net_income, dna, maintenance, wc)]
        return {"status": "ok", "value": values[0] + values[1] - abs(values[2]) - values[3], "formula": "net income + D&A - maintenance capex - normalized change in working capital", "source_fact_ids": _unique_ids(net_income, dna, maintenance, wc), "period": net_income.period}

    def _capex_analysis(self, fact_cache: dict[str, list[FinancialFact]], year: int | None) -> dict[str, Any]:
        total = self._fact_for_year(fact_cache["capital_expenditure"], year)
        maintenance = self._fact_for_year(fact_cache["maintenance_capex"], year)
        if total is None:
            return {"status": "insufficient_data", "total_capex": None, "maintenance_capex": None, "growth_capex": None, "missing_inputs": ["capital_expenditure"]}
        total_value = abs(_float(total.value) or 0)
        if maintenance is None:
            return {"status": "partial", "total_capex": total_value, "maintenance_capex": None, "growth_capex": None, "maintenance_vs_growth": "not_separately_reported", "missing_inputs": ["maintenance_capex"], "source_fact_ids": [total.id]}
        maintenance_value = abs(_float(maintenance.value) or 0)
        return {"status": "ok", "total_capex": total_value, "maintenance_capex": maintenance_value, "growth_capex": max(0, total_value - maintenance_value), "source_fact_ids": _unique_ids(total, maintenance)}

    def _what_must_be_true(
        self,
        *,
        assumptions: dict[str, Assumption],
        reverse_dcf: dict[str, Any],
        base_scenario: dict[str, Any] | None,
        fact_cache: dict[str, list[FinancialFact]],
        latest_year: int | None,
        market_opportunity: dict[str, Any],
    ) -> list[dict[str, Any]]:
        conditions: list[dict[str, Any]] = []
        growth = assumptions["revenue_growth"].value
        margin = assumptions["fcf_margin"].value
        if growth is not None:
            conditions.append({"id": "revenue_growth", "condition": f"Revenue CAGR must be at least {growth:.1%}", "value": growth, "unit": "decimal", "source_fact_ids": assumptions["revenue_growth"].source_fact_ids, "status": "monitor"})
        if margin is not None:
            conditions.append({"id": "fcf_margin", "condition": f"Normalized FCF margin must remain at least {margin:.1%}", "value": margin, "unit": "decimal", "source_fact_ids": assumptions["fcf_margin"].source_fact_ids, "status": "monitor"})
        if base_scenario and base_scenario.get("terminal_year", {}).get("roic") is not None:
            roic = base_scenario["terminal_year"]["roic"]
            wacc = assumptions["wacc"].value
            conditions.append({"id": "roic_above_wacc", "condition": "ROIC must remain above WACC to create value", "value": roic, "comparison": wacc, "unit": "decimal", "source_fact_ids": base_scenario["terminal_year"]["evidence"]["roic"]["source_fact_ids"], "status": "monitor"})
        if reverse_dcf.get("status") == "ok":
            required = reverse_dcf["required_revenue_growth"]
            conditions.append({"id": "price_expectations", "condition": f"The current price requires revenue growth of about {required:.1%}", "value": required, "unit": "decimal", "source_fact_ids": reverse_dcf.get("source_fact_ids", []), "status": "valuation_implied"})
        if self._fact_for_year(fact_cache["shares_diluted"], latest_year) is not None:
            conditions.append({"id": "share_count", "condition": "Share count must not expand faster than the model assumption", "value": assumptions["shares_cagr"].value, "unit": "decimal", "source_fact_ids": assumptions["shares_cagr"].source_fact_ids, "status": "monitor"})
        market_share = market_opportunity.get("market_share", {})
        conditions.append({
            "id": "competitive_position",
            "condition": "Market share must not deteriorate materially",
            "value": market_share.get("base_future_market_share"),
            "unit": "decimal",
            "source_fact_ids": market_share.get("source_fact_ids", []),
            "status": "monitor" if market_share.get("base_future_market_share") is not None else "blocked_missing_market_opportunity_data",
        })
        conditions.append({
            "id": "binding_constraint",
            "condition": f"The binding constraint must support the base case: {market_opportunity.get('constraints', {}).get('binding_constraint') or 'unknown'}",
            "value": None,
            "unit": "constraint",
            "source_fact_ids": market_opportunity.get("source_fact_ids", []),
            "status": "monitor" if market_opportunity.get("constraints", {}).get("binding_constraint") else "blocked_missing_market_opportunity_data",
        })
        return conditions

    def _timeline(self, db: Session, company_id: int) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for event in db.scalars(select(NewsEvent).where(NewsEvent.company_id == company_id).order_by(desc(NewsEvent.date)).limit(30)).all():
            events.append({"date": _date_value(event.date), "type": event.event_type, "title": event.title, "source": event.source, "source_url": event.url, "financial_impact": event.affected_assumptions, "thesis_impact": event.impact_direction, "moat_impact": "unknown", "management_credibility": "unknown"})
        for change in db.scalars(select(ThesisChange).where(ThesisChange.company_id == company_id).order_by(desc(ThesisChange.created_at)).limit(30)).all():
            events.append({"date": _date_value(change.created_at), "type": change.change_type, "title": change.summary, "source": "thesis_change", "source_url": None, "financial_impact": change.affected_metrics, "thesis_impact": change.impact_direction, "moat_impact": "unknown", "management_credibility": "unknown"})
        return sorted(events, key=lambda item: item.get("date") or "", reverse=True)[:40]

    def _coverage(self, history: list[dict[str, Any]], assumptions: dict[str, Assumption], scenarios: dict[str, Any]) -> dict[str, Any]:
        total = 0
        sourced = 0
        for row in history:
            for line in row.get("metrics", {}).values():
                if line.get("value") is not None:
                    total += 1
                    sourced += bool(line.get("source_fact_ids"))
        for assumption in assumptions.values():
            if assumption.value is not None:
                total += 1
                sourced += bool(assumption.source_fact_ids) or assumption.source_type == "model_policy"
        for scenario in scenarios.values():
            for item in scenario.get("forecast", []):
                for key in ("revenue", "free_cash_flow", "fcf_per_share"):
                    if item.get(key) is not None:
                        total += 1
                        sourced += bool(item.get("evidence", {}).get(key, {}).get("source_fact_ids"))
        return {"coverage_percent": round((sourced / total) * 100, 1) if total else 0, "sourced_values": sourced, "numeric_values": total, "rule": "Policy assumptions are disclosed separately; company numbers require source_fact_ids."}

    def _limitations(
        self,
        *,
        fact_cache: dict[str, list[FinancialFact]],
        years: list[int],
        missing_core: list[str],
        market_opportunity: dict[str, Any],
    ) -> list[str]:
        limitations = list(missing_core)
        if not fact_cache["working_capital"]:
            limitations.append("working_capital_and_absorption")
        if not fact_cache["maintenance_capex"]:
            limitations.append("maintenance_vs_growth_capex_split")
        if market_opportunity["status"] == "insufficient_data":
            limitations.append("market_opportunity")
        if len(years) < 5:
            limitations.append("full_10_year_history")
        return sorted(set(limitations))

    @staticmethod
    def _current_price(db: Session, company_id: int) -> float | None:
        position = db.scalar(select(Position).where(Position.company_id == company_id).limit(1))
        if position and _float(position.market_price) and (_float(position.market_price) or 0) > 0:
            return _float(position.market_price)
        market = db.scalar(select(MarketPrice).where(MarketPrice.company_id == company_id).order_by(desc(MarketPrice.date)).limit(1))
        return _float(market.close) if market and _float(market.close) and (_float(market.close) or 0) > 0 else None

    @staticmethod
    def _metric_value(value: float | None, unit: str, source_fact_ids: list[int], calculation: str) -> dict[str, Any]:
        return {"value": value, "unit": unit, "status": "calculated" if value is not None else "insufficient_data", "source_fact_ids": _unique_ids(ids=source_fact_ids), "calculation": calculation}

    def _ratio_metric(self, numerator: list[dict[str, Any]], denominator: list[dict[str, Any]], calculation: str) -> dict[str, Any]:
        denominator_by_year = {item["year"]: item for item in denominator}
        values: list[float] = []
        ids: list[int] = []
        for item in numerator:
            other = denominator_by_year.get(item["year"])
            if other and other["value"] not in (None, 0) and item["value"] is not None:
                values.append(item["value"] / other["value"])
                ids.extend(item["fact_ids"] + other["fact_ids"])
        return self._metric_value(median(values[-5:]) if values else None, "decimal", ids, calculation)

    @staticmethod
    def _fact_ids_for_metric(facts: list[FinancialFact]) -> list[int]:
        return [fact.id for fact in facts if fact.fiscal_year is not None and _is_annual(fact)]
