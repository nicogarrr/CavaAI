import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import CalculatedMetric, Company, FinancialFact


MetricFormula = tuple[str, str, tuple[str, ...], str]

CFROI_REQUIRED_INPUTS = (
    "gross_investment",
    "non_depreciating_assets",
    "inflation_adjusted_gross_cash_flow",
    "asset_life",
    "terminal_non_depreciating_assets",
)

METRIC_DEFINITIONS: dict[str, MetricFormula] = {
    "fcf_margin": ("FCF_MARGIN_V1", "free_cash_flow / revenue", ("free_cash_flow", "revenue"), "decimal"),
    "net_margin": ("NET_MARGIN_V1", "net_income / revenue", ("net_income", "revenue"), "decimal"),
    "operating_margin": ("OPERATING_MARGIN_V1", "operating_income / revenue", ("operating_income", "revenue"), "decimal"),
    "gross_margin": ("GROSS_MARGIN_V1", "gross_profit / revenue", ("gross_profit", "revenue"), "decimal"),
    "roe": ("ROE_V1", "net_income / total_equity", ("net_income", "total_equity"), "decimal"),
    "roa": ("ROA_V1", "net_income / total_assets", ("net_income", "total_assets"), "decimal"),
    "fcf_conversion": ("FCF_CONVERSION_V1", "free_cash_flow / net_income", ("free_cash_flow", "net_income"), "decimal"),
    "net_debt_to_ebitda": ("NET_DEBT_TO_EBITDA_V1", "net_debt / ebitda", ("net_debt", "ebitda"), "x"),
    "roic": (
        "ROIC_STANDARD_V2",
        "operating_income * (1 - effective_tax_rate) / average(total_debt + total_equity - cash_and_equivalents), using current invested capital when no coherent prior period exists",
        ("operating_income", "total_debt", "total_equity", "cash_and_equivalents"),
        "decimal",
    ),
    "roic_adjusted": (
        "ROIC_ADJUSTED_V1",
        "operating_income * (1 - effective_tax_rate) / adjusted_invested_capital, where adjusted_invested_capital = total_debt + total_equity - cash_and_equivalents - goodwill - intangible_assets + operating_lease_liabilities",
        (
            "operating_income",
            "total_debt",
            "total_equity",
            "cash_and_equivalents",
            "goodwill",
            "intangible_assets",
            "operating_lease_liabilities",
        ),
        "decimal",
    ),
    "wacc": (
        "WACC_STANDARD_V1",
        "equity_weight * (risk_free_rate + beta * equity_risk_premium + country_risk_premium) + debt_weight * cost_of_debt * (1 - tax_rate)",
        ("risk_free_rate", "beta", "equity_risk_premium", "total_debt"),
        "decimal",
    ),
    "cfroi": (
        "CFROI_V1",
        "inflation-adjusted internal rate of return on gross investment; no proxy calculation is permitted",
        CFROI_REQUIRED_INPUTS,
        "decimal",
    ),
}


@dataclass
class MetricResult:
    metric: str
    status: str
    period: str
    value: Decimal | None
    unit: str
    definition_version: str
    formula: str
    numerator: Decimal | None
    denominator: Decimal | None
    source_fact_ids: list[int]
    calculation_trace: dict
    confidence: Decimal
    fiscal_year: int | None = None
    fiscal_quarter: str | None = None
    id: int | None = None


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)


class MetricCalculationService:
    def calculate_all(self, db: Session, company: Company, persist: bool = True) -> list[MetricResult]:
        results = [self.calculate(db, company, metric, persist=persist) for metric in METRIC_DEFINITIONS]
        if persist:
            db.commit()
        return results

    def calculate(self, db: Session, company: Company, metric: str, persist: bool = True) -> MetricResult:
        if metric not in METRIC_DEFINITIONS:
            raise ValueError(f"Unsupported calculated metric: {metric}")
        definition_version, formula, inputs, unit = METRIC_DEFINITIONS[metric]

        if metric == "wacc":
            return self._calculate_wacc(db, company, persist)
        if metric == "cfroi":
            return self._calculate_cfroi(db, company, persist)

        facts = self._coherent_facts(
            db,
            company,
            inputs,
            strict=metric in {"roic", "roic_adjusted"},
        )
        missing_inputs = [input_metric for input_metric in inputs if input_metric not in facts]
        period = self._period_for_result(facts)

        if missing_inputs:
            first = next(iter(facts.values()), None)
            result = MetricResult(
                metric=metric,
                status="unavailable",
                period=period,
                value=None,
                unit=unit,
                definition_version=definition_version,
                formula=formula,
                numerator=None,
                denominator=None,
                source_fact_ids=[fact.id for fact in facts.values()],
                calculation_trace={
                    "reason": (
                        "missing_or_incoherent_inputs"
                        if metric in {"roic", "roic_adjusted"}
                        else "missing_inputs"
                    ),
                    "missing_inputs": missing_inputs,
                    "available_inputs": sorted(facts),
                },
                confidence=Decimal("0.00"),
                fiscal_year=first.fiscal_year if first else None,
                fiscal_quarter=first.fiscal_quarter if first else None,
            )
            return self._persist_if_requested(db, company, result, persist)

        numerator, denominator, trace, supplemental_facts = self._evaluate(
            db,
            company,
            metric,
            facts,
        )
        result_facts = {**facts, **supplemental_facts}
        unique_facts = self._unique_facts(result_facts)
        if denominator is None or denominator == 0 or numerator is None:
            result = MetricResult(
                metric=metric,
                status="unavailable",
                period=period,
                value=None,
                unit=unit,
                definition_version=definition_version,
                formula=formula,
                numerator=numerator,
                denominator=denominator,
                source_fact_ids=[fact.id for fact in unique_facts],
                calculation_trace={
                    **trace,
                    "reason": "zero_or_invalid_denominator",
                },
                confidence=Decimal("0.00"),
                fiscal_year=next(iter(facts.values())).fiscal_year if facts else None,
                fiscal_quarter=next(iter(facts.values())).fiscal_quarter if facts else None,
            )
            return self._persist_if_requested(db, company, result, persist)

        value = _quantize(numerator / denominator)
        confidence = min(
            (Decimal(fact.confidence) for fact in unique_facts),
            default=Decimal("0.70"),
        )
        if trace.get("tax_rate_source") == "statutory_fallback":
            confidence = min(confidence, Decimal("0.70"))
        result = MetricResult(
            metric=metric,
            status="ok",
            period=period,
            value=value,
            unit=unit,
            definition_version=definition_version,
            formula=formula,
            numerator=_quantize(numerator),
            denominator=_quantize(denominator),
            source_fact_ids=[fact.id for fact in unique_facts],
            calculation_trace={
                **trace,
                "inputs": {
                    input_metric: {
                        "fact_id": fact.id,
                        "value": str(fact.value),
                        "period": fact.period,
                        "source_type": fact.source_type,
                        "metric": fact.metric,
                    }
                    for input_metric, fact in result_facts.items()
                },
            },
            confidence=confidence,
            fiscal_year=next(iter(facts.values())).fiscal_year if facts else None,
            fiscal_quarter=next(iter(facts.values())).fiscal_quarter if facts else None,
        )

        return self._persist_if_requested(db, company, result, persist)

    def latest_calculated(self, db: Session, company: Company) -> list[CalculatedMetric]:
        return list(
            db.scalars(
                select(CalculatedMetric)
                .where(CalculatedMetric.company_id == company.id)
                .order_by(CalculatedMetric.metric, desc(CalculatedMetric.updated_at))
            ).all()
        )

    def _coherent_facts(
        self,
        db: Session,
        company: Company,
        inputs: tuple[str, ...],
        strict: bool = False,
    ) -> dict[str, FinancialFact]:
        anchors = self._facts_for_metric(db, company, inputs[0])
        best_match: dict[str, FinancialFact] = {}
        for anchor in anchors:
            facts = {inputs[0]: anchor}
            for metric in inputs[1:]:
                match = self._match_fact(db, company, metric, anchor)
                if match:
                    facts[metric] = match
            if len(facts) == len(inputs):
                return facts
            if len(facts) > len(best_match):
                best_match = facts
        if strict:
            return best_match
        facts: dict[str, FinancialFact] = {}
        for metric in inputs:
            latest = self._facts_for_metric(db, company, metric)
            if latest:
                facts[metric] = latest[0]
        return facts

    def _facts_for_metric(self, db: Session, company: Company, metric: str) -> list[FinancialFact]:
        return list(
            db.scalars(
                select(FinancialFact)
                .where(FinancialFact.company_id == company.id, FinancialFact.metric == metric)
                .order_by(FinancialFact.fiscal_year.desc().nullslast(), desc(FinancialFact.created_at))
                .limit(20)
            ).all()
        )

    def _match_fact(self, db: Session, company: Company, metric: str, anchor: FinancialFact) -> FinancialFact | None:
        candidates = self._facts_for_metric(db, company, metric)
        for candidate in candidates:
            if candidate.period == anchor.period:
                return candidate
        for candidate in candidates:
            if (
                anchor.fiscal_year is not None
                and candidate.fiscal_year == anchor.fiscal_year
                and candidate.fiscal_quarter == anchor.fiscal_quarter
            ):
                return candidate
        return None

    def _period_for_result(self, facts: dict[str, FinancialFact]) -> str:
        if not facts:
            return "unknown"
        first = next(iter(facts.values()))
        return first.period

    def _evaluate(
        self,
        db: Session,
        company: Company,
        metric: str,
        facts: dict[str, FinancialFact],
    ) -> tuple[Decimal | None, Decimal | None, dict, dict[str, FinancialFact]]:
        value = lambda key: Decimal(facts[key].value)
        if metric in {"roic", "roic_adjusted"}:
            tax_rate, tax_trace, tax_facts = self._tax_rate_for_period(
                db,
                company,
                facts["operating_income"],
                allow_fallback=True,
            )
            assert tax_rate is not None
            nopat = value("operating_income") * (Decimal("1") - tax_rate)
            capital_metrics = ["total_debt", "total_equity", "cash_and_equivalents"]
            current_invested_capital = (
                value("total_debt")
                + value("total_equity")
                - value("cash_and_equivalents")
            )
            if metric == "roic_adjusted":
                capital_metrics.extend(
                    ["goodwill", "intangible_assets", "operating_lease_liabilities"]
                )
                current_invested_capital = (
                    current_invested_capital
                    - value("goodwill")
                    - value("intangible_assets")
                    + value("operating_lease_liabilities")
                )

            prior = self._prior_coherent_facts(
                db,
                company,
                facts["operating_income"],
                tuple(capital_metrics),
            )
            supplemental_facts = dict(tax_facts)
            prior_invested_capital = None
            invested_capital = current_invested_capital
            capital_basis = "current_period"
            if prior:
                prior_invested_capital = (
                    Decimal(prior["total_debt"].value)
                    + Decimal(prior["total_equity"].value)
                    - Decimal(prior["cash_and_equivalents"].value)
                )
                if metric == "roic_adjusted":
                    prior_invested_capital = (
                        prior_invested_capital
                        - Decimal(prior["goodwill"].value)
                        - Decimal(prior["intangible_assets"].value)
                        + Decimal(prior["operating_lease_liabilities"].value)
                    )
                invested_capital = (
                    current_invested_capital + prior_invested_capital
                ) / Decimal("2")
                capital_basis = "average_current_and_prior_period"
                supplemental_facts.update(
                    {f"prior_{key}": fact for key, fact in prior.items()}
                )

            trace = {
                "method": (
                    "adjusted_roic" if metric == "roic_adjusted" else "standard_roic"
                ),
                **tax_trace,
                "nopat": str(nopat),
                "invested_capital": str(invested_capital),
                "invested_capital_basis": capital_basis,
                "current_invested_capital": str(current_invested_capital),
                "prior_invested_capital": (
                    str(prior_invested_capital)
                    if prior_invested_capital is not None
                    else None
                ),
            }
            if metric == "roic_adjusted":
                trace["adjustments"] = {
                    "goodwill_removed": str(value("goodwill")),
                    "intangible_assets_removed": str(value("intangible_assets")),
                    "operating_lease_liabilities_added": str(
                        value("operating_lease_liabilities")
                    ),
                    "numerator_adjustments": (
                        "none; no amortization or lease-interest add-back is made "
                        "without separately reported inputs"
                    ),
                }
            return nopat, invested_capital, trace, supplemental_facts
        numerator_key, denominator_key = METRIC_DEFINITIONS[metric][2]
        return (
            value(numerator_key),
            value(denominator_key),
            {
                "method": "simple_ratio",
                "numerator_metric": numerator_key,
                "denominator_metric": denominator_key,
            },
            {},
        )

    def _tax_rate_for_period(
        self,
        db: Session,
        company: Company,
        anchor: FinancialFact,
        allow_fallback: bool,
        allow_latest: bool = False,
    ) -> tuple[Decimal | None, dict, dict[str, FinancialFact]]:
        direct = self._match_alias(
            db,
            company,
            ("effective_tax_rate", "tax_rate"),
            anchor,
            reported_only=True,
            allow_latest=allow_latest,
        )
        rejected_inputs: list[str] = []
        if direct:
            _, fact = direct
            rate, normalized = self._normalize_rate(fact.value)
            if rate is not None and Decimal("0") <= rate <= Decimal("1"):
                return rate, {
                    "tax_rate": str(rate),
                    "tax_rate_source": "reported_effective_tax_rate",
                    "tax_rate_fallback": False,
                    "tax_rate_normalized_from_percent": normalized,
                    "tax_rate_input_fact_ids": [fact.id],
                }, {"effective_tax_rate": fact}
            rejected_inputs.append(f"{fact.metric}:outside_0_to_1")

        tax_expense = self._match_alias(
            db,
            company,
            ("income_tax_expense", "tax_expense"),
            anchor,
            reported_only=True,
            allow_latest=allow_latest,
        )
        pretax_anchor = tax_expense[1] if tax_expense else anchor
        pretax_income = self._match_alias(
            db,
            company,
            ("income_before_tax", "pretax_income", "income_before_taxes"),
            pretax_anchor,
            reported_only=True,
        )
        if tax_expense and pretax_income:
            _, expense_fact = tax_expense
            _, pretax_fact = pretax_income
            pretax = Decimal(pretax_fact.value)
            if pretax > 0:
                derived_rate = Decimal(expense_fact.value) / pretax
                if Decimal("0") <= derived_rate <= Decimal("1"):
                    return derived_rate, {
                        "tax_rate": str(derived_rate),
                        "tax_rate_source": "reported_income_statement",
                        "tax_rate_fallback": False,
                        "tax_rate_formula": "income_tax_expense / income_before_tax",
                        "tax_rate_input_fact_ids": [
                            expense_fact.id,
                            pretax_fact.id,
                        ],
                    }, {
                        "income_tax_expense": expense_fact,
                        "income_before_tax": pretax_fact,
                    }
            rejected_inputs.append("income_tax_expense/income_before_tax:incoherent")

        if not allow_fallback:
            return None, {
                "tax_rate": None,
                "tax_rate_source": "unavailable",
                "tax_rate_fallback": False,
                "rejected_tax_inputs": rejected_inputs,
            }, {}

        fallback = Decimal("0.21")
        return fallback, {
            "tax_rate": str(fallback),
            "tax_rate_source": "statutory_fallback",
            "tax_rate_fallback": True,
            "tax_rate_fallback_reason": (
                "no coherent reported effective tax rate or reported "
                "income-tax-expense/pre-tax-income pair"
            ),
            "rejected_tax_inputs": rejected_inputs,
            "confidence_adjustment": "capped_at_0.70_for_tax_fallback",
        }, {}

    def _prior_coherent_facts(
        self,
        db: Session,
        company: Company,
        current_anchor: FinancialFact,
        metrics: tuple[str, ...],
    ) -> dict[str, FinancialFact]:
        for prior_anchor in self._facts_for_metric(db, company, metrics[0]):
            if not self._is_prior_period(prior_anchor, current_anchor):
                continue
            facts = {metrics[0]: prior_anchor}
            for metric in metrics[1:]:
                match = self._match_fact(db, company, metric, prior_anchor)
                if match:
                    facts[metric] = match
            if len(facts) == len(metrics):
                return facts
        return {}

    def _is_prior_period(
        self,
        candidate: FinancialFact,
        current: FinancialFact,
    ) -> bool:
        if candidate.fiscal_year is not None and current.fiscal_year is not None:
            if candidate.fiscal_year >= current.fiscal_year:
                return False
            if (
                candidate.fiscal_quarter is not None
                and current.fiscal_quarter is not None
                and candidate.fiscal_quarter != current.fiscal_quarter
            ):
                return False
            return True
        return candidate.period < current.period

    def _match_alias(
        self,
        db: Session,
        company: Company,
        aliases: tuple[str, ...],
        anchor: FinancialFact,
        reported_only: bool = False,
        allow_latest: bool = False,
    ) -> tuple[str, FinancialFact] | None:
        for alias in aliases:
            for candidate in self._facts_for_metric(db, company, alias):
                if reported_only and not candidate.is_reported:
                    continue
                if self._same_period(candidate, anchor):
                    return alias, candidate
        if allow_latest:
            for alias in aliases:
                for candidate in self._facts_for_metric(db, company, alias):
                    if not reported_only or candidate.is_reported:
                        return alias, candidate
        return None

    def _same_period(self, candidate: FinancialFact, anchor: FinancialFact) -> bool:
        if candidate.period == anchor.period:
            return True
        return (
            anchor.fiscal_year is not None
            and candidate.fiscal_year == anchor.fiscal_year
            and candidate.fiscal_quarter == anchor.fiscal_quarter
        )

    def _normalize_rate(
        self,
        raw_value: Decimal,
        allow_negative: bool = False,
    ) -> tuple[Decimal | None, bool]:
        rate = Decimal(raw_value)
        if rate > 1 and rate <= 100:
            rate /= Decimal("100")
            normalized = True
        else:
            normalized = False
        if rate < 0 and not allow_negative:
            return None, normalized
        if rate > 1:
            return None, normalized
        return rate, normalized

    def _calculate_wacc(
        self,
        db: Session,
        company: Company,
        persist: bool,
    ) -> MetricResult:
        definition_version, formula, _, unit = METRIC_DEFINITIONS["wacc"]
        anchors = self._facts_for_metric(db, company, "risk_free_rate")
        if not anchors:
            result = MetricResult(
                metric="wacc",
                status="unavailable",
                period="unknown",
                value=None,
                unit=unit,
                definition_version=definition_version,
                formula=formula,
                numerator=None,
                denominator=None,
                source_fact_ids=[],
                calculation_trace={
                    "method": "standard_wacc",
                    "reason": "missing_or_incoherent_inputs",
                    "missing_inputs": ["risk_free_rate"],
                },
                confidence=Decimal("0.00"),
            )
            return self._persist_if_requested(db, company, result, persist)

        best_facts: dict[str, FinancialFact] = {"risk_free_rate": anchors[0]}
        best_missing: list[str] = []
        best_tax_trace: dict = {}
        for anchor in anchors:
            facts: dict[str, FinancialFact] = {"risk_free_rate": anchor}
            missing: list[str] = []
            for key, aliases in (
                ("beta", ("beta",)),
                ("equity_risk_premium", ("equity_risk_premium",)),
                ("total_debt", ("total_debt",)),
            ):
                matched = self._match_alias(
                    db,
                    company,
                    aliases,
                    anchor,
                    allow_latest=True,
                )
                if matched:
                    facts[key] = matched[1]
                else:
                    missing.append(key)

            equity = self._match_alias(
                db,
                company,
                ("market_cap", "market_capitalization", "total_equity"),
                anchor,
                allow_latest=True,
            )
            if equity:
                facts["equity_value"] = equity[1]
            else:
                missing.append("market_cap_or_total_equity")

            tax_rate, tax_trace, tax_facts = self._tax_rate_for_period(
                db,
                company,
                anchor,
                allow_fallback=False,
                allow_latest=True,
            )
            facts.update(tax_facts)
            if tax_rate is None:
                missing.append("tax_rate")

            cost_of_debt = None
            cost_of_debt_source = None
            direct_debt_cost = self._match_alias(
                db,
                company,
                ("cost_of_debt",),
                anchor,
                allow_latest=True,
            )
            if direct_debt_cost:
                facts["cost_of_debt"] = direct_debt_cost[1]
                cost_of_debt, _ = self._normalize_rate(direct_debt_cost[1].value)
                cost_of_debt_source = "reported_cost_of_debt"
                if cost_of_debt is None:
                    missing.append("valid_cost_of_debt")
            elif "total_debt" in facts and Decimal(facts["total_debt"].value) > 0:
                interest = self._match_alias(
                    db,
                    company,
                    ("interest_expense",),
                    facts["total_debt"],
                    allow_latest=True,
                )
                if interest:
                    facts["interest_expense"] = interest[1]
                    cost_of_debt = (
                        abs(Decimal(interest[1].value))
                        / Decimal(facts["total_debt"].value)
                    )
                    cost_of_debt_source = "interest_expense_over_debt"
                    if cost_of_debt > 1:
                        cost_of_debt = None
                        missing.append("valid_interest_expense_over_debt")
                else:
                    missing.append("cost_of_debt_or_interest_expense")
            else:
                missing.append("cost_of_debt_or_interest_expense")

            if not missing:
                country_risk = self._match_alias(
                    db,
                    company,
                    ("country_risk_premium",),
                    anchor,
                    allow_latest=True,
                )
                country_risk_rate = Decimal("0")
                if country_risk:
                    facts["country_risk_premium"] = country_risk[1]
                    normalized_country_risk, _ = self._normalize_rate(
                        country_risk[1].value
                    )
                    if normalized_country_risk is None:
                        missing.append("valid_country_risk_premium")
                    else:
                        country_risk_rate = normalized_country_risk

            if len(facts) >= len(best_facts):
                best_facts = facts
                best_missing = missing
                best_tax_trace = tax_trace
            if missing:
                continue

            risk_free_rate, rf_normalized = self._normalize_rate(
                facts["risk_free_rate"].value,
                allow_negative=True,
            )
            equity_risk_premium, erp_normalized = self._normalize_rate(
                facts["equity_risk_premium"].value
            )
            beta = Decimal(facts["beta"].value)
            debt = Decimal(facts["total_debt"].value)
            equity_value = Decimal(facts["equity_value"].value)
            if (
                risk_free_rate is None
                or equity_risk_premium is None
                or debt < 0
                or equity_value <= 0
                or debt + equity_value <= 0
            ):
                best_facts = facts
                best_missing = ["valid_rates_and_capital_weights"]
                best_tax_trace = tax_trace
                continue

            country_risk_rate = (
                self._normalize_rate(facts["country_risk_premium"].value)[0]
                if "country_risk_premium" in facts
                else Decimal("0")
            )
            assert country_risk_rate is not None
            assert tax_rate is not None
            assert cost_of_debt is not None
            cost_of_equity = (
                risk_free_rate
                + beta * equity_risk_premium
                + country_risk_rate
            )
            total_capital = equity_value + debt
            equity_weight = equity_value / total_capital
            debt_weight = debt / total_capital
            after_tax_cost_of_debt = cost_of_debt * (Decimal("1") - tax_rate)
            wacc = (
                equity_weight * cost_of_equity
                + debt_weight * after_tax_cost_of_debt
            )
            unique_facts = self._unique_facts(facts)
            as_of_date = self._date_from_period(anchor.period)
            trace = {
                "method": "standard_wacc",
                **tax_trace,
                "risk_free_rate": str(risk_free_rate),
                "beta": str(beta),
                "equity_risk_premium": str(equity_risk_premium),
                "country_risk_premium": str(country_risk_rate),
                "cost_of_equity": str(cost_of_equity),
                "cost_of_debt": str(cost_of_debt),
                "cost_of_debt_source": cost_of_debt_source,
                "after_tax_cost_of_debt": str(after_tax_cost_of_debt),
                "equity_value": str(equity_value),
                "equity_value_source": facts["equity_value"].metric,
                "debt": str(debt),
                "equity_weight": str(equity_weight),
                "debt_weight": str(debt_weight),
                "currency": company.currency,
                "as_of_period": anchor.period,
                "input_period_alignment": (
                    "same_period"
                    if len({fact.period for fact in facts.values()}) == 1
                    else "mixed_latest_available"
                ),
                "rate_normalization": {
                    "risk_free_rate_from_percent": rf_normalized,
                    "equity_risk_premium_from_percent": erp_normalized,
                },
                "inputs": {
                    key: {
                        "fact_id": fact.id,
                        "metric": fact.metric,
                        "value": str(fact.value),
                        "period": fact.period,
                        "source_type": fact.source_type,
                        "unit": fact.unit,
                    }
                    for key, fact in facts.items()
                },
            }
            if as_of_date:
                trace["as_of_date"] = as_of_date
            result = MetricResult(
                metric="wacc",
                status="ok",
                period=anchor.period,
                value=_quantize(wacc),
                unit=unit,
                definition_version=definition_version,
                formula=formula,
                numerator=_quantize(wacc),
                denominator=Decimal("1.00000000"),
                source_fact_ids=[fact.id for fact in unique_facts],
                calculation_trace=trace,
                confidence=min(
                    Decimal(fact.confidence) for fact in unique_facts
                ),
                fiscal_year=anchor.fiscal_year,
                fiscal_quarter=anchor.fiscal_quarter,
            )
            return self._persist_if_requested(db, company, result, persist)

        anchor = anchors[0]
        unique_facts = self._unique_facts(best_facts)
        result = MetricResult(
            metric="wacc",
            status="unavailable",
            period=anchor.period,
            value=None,
            unit=unit,
            definition_version=definition_version,
            formula=formula,
            numerator=None,
            denominator=None,
            source_fact_ids=[fact.id for fact in unique_facts],
            calculation_trace={
                "method": "standard_wacc",
                **best_tax_trace,
                "reason": "missing_or_incoherent_inputs",
                "missing_inputs": sorted(set(best_missing)),
                "available_inputs": sorted(best_facts),
                "currency": company.currency,
                "as_of_period": anchor.period,
            },
            confidence=Decimal("0.00"),
            fiscal_year=anchor.fiscal_year,
            fiscal_quarter=anchor.fiscal_quarter,
        )
        return self._persist_if_requested(db, company, result, persist)

    def _calculate_cfroi(
        self,
        db: Session,
        company: Company,
        persist: bool,
    ) -> MetricResult:
        definition_version, formula, _, unit = METRIC_DEFINITIONS["cfroi"]
        available: dict[str, FinancialFact] = {}
        for input_metric in CFROI_REQUIRED_INPUTS:
            facts = self._facts_for_metric(db, company, input_metric)
            if facts:
                available[input_metric] = facts[0]
        first = next(iter(available.values()), None)
        result = MetricResult(
            metric="cfroi",
            status="unavailable",
            period=first.period if first else "unknown",
            value=None,
            unit=unit,
            definition_version=definition_version,
            formula=formula,
            numerator=None,
            denominator=None,
            source_fact_ids=[
                fact.id for fact in self._unique_facts(available)
            ],
            calculation_trace={
                "method": "cfroi",
                "reason": "specialized_methodology_inputs_required",
                "methodology": (
                    "CFROI requires inflation-adjusted gross cash flow, "
                    "inflation-adjusted gross investment, asset-life normalization, "
                    "and terminal non-depreciating assets; accounting proxies are "
                    "not substituted."
                ),
                "required_inputs": list(CFROI_REQUIRED_INPUTS),
                "missing_inputs": [
                    key for key in CFROI_REQUIRED_INPUTS if key not in available
                ],
                "policy": "persist_unavailable_never_fabricate",
            },
            confidence=Decimal("0.00"),
            fiscal_year=first.fiscal_year if first else None,
            fiscal_quarter=first.fiscal_quarter if first else None,
        )
        return self._persist_if_requested(db, company, result, persist)

    def _date_from_period(self, period: str) -> str | None:
        match = re.match(r"^\d{4}-\d{2}-\d{2}", period)
        return match.group(0) if match else None

    def _unique_facts(
        self,
        facts: dict[str, FinancialFact],
    ) -> list[FinancialFact]:
        unique: dict[int, FinancialFact] = {}
        for fact in facts.values():
            unique[fact.id] = fact
        return list(unique.values())

    def _persist_if_requested(
        self,
        db: Session,
        company: Company,
        result: MetricResult,
        persist: bool,
    ) -> MetricResult:
        if persist:
            stored = self._upsert(db, company, result)
            result.id = stored.id
        return result

    def _upsert(self, db: Session, company: Company, result: MetricResult) -> CalculatedMetric:
        metric = db.scalar(
            select(CalculatedMetric).where(
                CalculatedMetric.company_id == company.id,
                CalculatedMetric.metric == result.metric,
                CalculatedMetric.period == result.period,
                CalculatedMetric.definition_version == result.definition_version,
            )
        )
        if metric is None:
            metric = CalculatedMetric(
                company_id=company.id,
                metric=result.metric,
                period=result.period,
                definition_version=result.definition_version,
                formula=result.formula,
            )
            db.add(metric)

        metric.value = result.value
        metric.unit = result.unit
        metric.fiscal_year = result.fiscal_year
        metric.fiscal_quarter = result.fiscal_quarter
        metric.status = result.status
        metric.formula = result.formula
        metric.numerator = result.numerator
        metric.denominator = result.denominator
        metric.source_fact_ids = result.source_fact_ids
        metric.calculation_trace = result.calculation_trace
        metric.confidence = result.confidence
        db.flush()
        return metric
