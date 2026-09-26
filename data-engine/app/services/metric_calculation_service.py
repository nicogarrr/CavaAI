import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import delete, desc, select
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

# Métricas del marco de calidad de Nico: medias de ratios anuales en una
# ventana de hasta 5 años fiscales (mínimo 3). metric -> (numerador, denominador)
WINDOWED_RATIO_METRICS: dict[str, tuple[str, str]] = {
    "fcf_margin_5y": ("free_cash_flow", "revenue"),
    "net_margin_5y": ("net_income", "revenue"),
    "roe_5y": ("net_income", "total_equity"),
    "roa_5y": ("net_income", "total_assets"),
}

WINDOW_MIN_YEARS = 3
WINDOW_MAX_YEARS = 5

# Umbrales MARCO_NICO_V2 (criterios estandar value/Buffett; Nico delego la
# eleccion el 2026-09-25: "usa los criterios que veas convenientes").
# Documentados en /metodologia para que pueda ajustarlos despues:
# - owner earnings (Buffett, carta 1986): la media de hasta 5 anos debe ser
#   positiva.
# - intensidad de capex: |capex|/D&A medio <= 1.5 (1.0 = solo mantenimiento;
#   hasta 1.5 admite crecimiento sin ser devorador de capital).
# - CFROI (aprox declarada) > WACC: creacion de valor en terminos de caja,
#   complementario al ROIC > WACC contable.
V2_OWNER_EARNINGS_MIN = Decimal("0")
V2_CAPEX_TO_DA_MAX = Decimal("1.5")

# Metricas compuestas con ventana propia (no caben en WINDOWED_RATIO_METRICS).
WINDOWED_COMPOSED_METRICS = ("owner_earnings_5y", "capex_to_da_5y")

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
    "fcf_margin_5y": (
        "FCF_MARGIN_5Y_V1",
        "mean of annual free_cash_flow / revenue over up to 5 most recent fiscal years, minimum 3; coverage declared in trace",
        ("free_cash_flow", "revenue"),
        "decimal",
    ),
    "net_margin_5y": (
        "NET_MARGIN_5Y_V1",
        "mean of annual net_income / revenue over up to 5 most recent fiscal years, minimum 3; coverage declared in trace",
        ("net_income", "revenue"),
        "decimal",
    ),
    "roe_5y": (
        "ROE_5Y_V1",
        "mean of annual net_income / total_equity over up to 5 most recent fiscal years, minimum 3; coverage declared in trace",
        ("net_income", "total_equity"),
        "decimal",
    ),
    "roa_5y": (
        "ROA_5Y_V1",
        "mean of annual net_income / total_assets over up to 5 most recent fiscal years, minimum 3; coverage declared in trace",
        ("net_income", "total_assets"),
        "decimal",
    ),
    "owner_earnings": (
        "OWNER_EARNINGS_V1",
        "net_income + depreciation_amortization - maintenance_capex, where maintenance_capex = min(abs(capital_expenditure), depreciation_amortization); maintenance capex is not separately reported - declared conservative estimate (Buffet owner earnings)",
        ("net_income", "depreciation_amortization", "capital_expenditure"),
        "USD",
    ),
    "cfroi_approx": (
        "CFROI_APPROX_V1",
        "approximate CFROI: (net_income + depreciation_amortization + interest_expense * (1 - effective_tax_rate)) / total_assets; DECLARED approximation - invested capital proxied by total_assets, no inflation adjustment, not comparable to Credit Suisse CFROI",
        ("net_income", "depreciation_amortization", "interest_expense", "total_assets"),
        "decimal",
    ),
    "owner_earnings_5y": (
        "OWNER_EARNINGS_5Y_V1",
        "mean of annual (net_income + depreciation_amortization - min(abs(capital_expenditure), depreciation_amortization)) over up to 5 most recent fiscal years, minimum 3; maintenance capex is a declared conservative estimate (Buffett owner earnings)",
        ("net_income", "depreciation_amortization", "capital_expenditure"),
        "USD",
    ),
    "capex_to_da_5y": (
        "CAPEX_TO_DA_5Y_V1",
        "mean of annual abs(capital_expenditure) / depreciation_amortization over up to 5 most recent fiscal years, minimum 3; 1.0 = maintenance-only investment, higher = growth or capital intensity",
        ("capital_expenditure", "depreciation_amortization"),
        "decimal",
    ),
    # Marco de calidad de Nico (apuntes manuscritos, sept 2026): 5 checks
    # trazables. Cada check no evaluable queda declarado como null, nunca
    # cuenta como superado.
    "quality_moat_score": (
        "MARCO_NICO_V1",
        "count of passed checks: fcf_margin_5y > 0.05, net_margin_5y > 0.15, roe_5y > 0.15, roa_5y > 0.07, roic > wacc; each check traceable with its value and threshold",
        (),
        "score",
    ),
    # V2 (2026-09-25): los 5 checks de V1 mas tres de caja y disciplina de
    # capital. Umbrales elegidos por delegacion de Nico y documentados en
    # /metodologia; cada check no evaluable queda null, nunca cuenta.
    "quality_moat_score_v2": (
        "MARCO_NICO_V2",
        "V1 checks (fcf_margin_5y > 0.05, net_margin_5y > 0.15, roe_5y > 0.15, roa_5y > 0.07, roic > wacc) plus cfroi_approx > wacc, owner_earnings_5y > 0, capex_to_da_5y <= 1.5; each check traceable with its value and threshold",
        (),
        "score",
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


# Fuentes cuyos importes monetarios llegan en unidades absolutas: market data
# (yfinance, Finnhub) y hechos SEC/FMP. Entre ellas, con la misma unidad, un
# ratio extremo entre capitalizacion y deuda es estructura de capital real
# (una mega-cap casi sin deuda), NO un error de unidades.
_ABSOLUTE_AMOUNT_SOURCES = frozenset({"yfinance", "Finnhub", "SEC", "FMP"})


def _capital_scale_conflict(equity_fact: FinancialFact, debt_fact: FinancialFact) -> bool:
    """True si equity y debt no son comparables para el WACC.

    Fail-closed, en este orden:
    - Unidades monetarias explicitas y distintas (USD vs EUR): conflicto
      siempre. No es un error de escala sino de divisa, y ninguna
      provenance lo rescata: un par de fuentes "absolutas" no es
      comparable si cada una expresa otra moneda.
    - Ambas fuentes absolutas y misma unidad: comparables a cualquier
      ratio (una mega-cap casi sin deuda supera 100x de forma real).
    - Cualquier otra combinacion (ESEF sin escala persistida, o
      provenance incierta): conflicto siempre, a cualquier magnitud.
      Un ratio razonable no demuestra unidades compatibles; el atajo
      del 100x dejaba pasar mezclas no verificables.

    Nunca se deduce un factor de escala ni de divisa: si no son
    comparables, el metodo queda unavailable en vez de publicar un WACC
    inventado.
    """
    if debt_fact.value == 0:
        return False
    if (
        equity_fact.unit
        and debt_fact.unit
        and equity_fact.unit != debt_fact.unit
    ):
        return True
    if (
        equity_fact.source_type in _ABSOLUTE_AMOUNT_SOURCES
        and debt_fact.source_type in _ABSOLUTE_AMOUNT_SOURCES
        and equity_fact.unit == debt_fact.unit
    ):
        return False
    return True


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
        if metric in WINDOWED_RATIO_METRICS:
            return self._calculate_windowed_ratio(db, company, metric, persist)
        if metric in WINDOWED_COMPOSED_METRICS:
            return self._calculate_windowed_composed(db, company, metric, persist)
        if metric == "quality_moat_score":
            return self._calculate_quality_score(db, company, persist)
        if metric == "quality_moat_score_v2":
            return self._calculate_quality_score_v2(db, company, persist)

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
        if metric == "owner_earnings":
            net_income = value("net_income")
            depreciation = value("depreciation_amortization")
            capex_abs = abs(value("capital_expenditure"))
            maintenance_capex = min(capex_abs, depreciation)
            trace = {
                "method": "owner_earnings",
                "maintenance_capex": str(_quantize(maintenance_capex)),
                "maintenance_capex_rule": (
                    "min(abs(capital_expenditure), depreciation_amortization); "
                    "maintenance capex is not separately reported - declared "
                    "conservative estimate"
                ),
                "estimated_growth_capex": str(_quantize(capex_abs - maintenance_capex)),
            }
            return net_income + depreciation - maintenance_capex, Decimal("1"), trace, {}
        if metric == "cfroi_approx":
            tax_rate, tax_trace, tax_facts = self._tax_rate_for_period(
                db,
                company,
                facts["net_income"],
                allow_fallback=True,
            )
            assert tax_rate is not None
            gross_cash_flow = (
                value("net_income")
                + value("depreciation_amortization")
                + value("interest_expense") * (Decimal("1") - tax_rate)
            )
            trace = {
                "method": "cfroi_approx",
                "approximation": (
                    "invested capital proxied by total_assets; no inflation "
                    "adjustment; not comparable to Credit Suisse CFROI"
                ),
                **tax_trace,
            }
            return gross_cash_flow, value("total_assets"), trace, tax_facts
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

            # Solo valor de MERCADO para el peso de equity. `total_equity` es el
            # patrimonio contable: usarlo como Ew del WACC mezcla market value
            # con book value. Con market cap 10.000M, book equity 2.000M y debt
            # 3.000M, el WACC correcto es 7,08% y con book equity salia 5,60%
            # (-21%), y como el DCF escala con 1/(WACC-g) el valor de salida se
            # desvía +48%. Si no hay market cap, el WACC no se calcula: se
            # declara unavailable con el motivo (ver mas abajo).
            equity = self._match_alias(
                db,
                company,
                ("market_cap", "market_capitalization"),
                anchor,
                allow_latest=True,
            )
            if equity:
                facts["equity_value"] = equity[1]
            else:
                missing.append("market_cap")

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
            if _capital_scale_conflict(facts["equity_value"], facts["total_debt"]):
                # market_cap viene de market data en unidades absolutas;
                # total_debt ESEF puede llegar escalado (scale no se conserva).
                # Sumarlos sin reconciliar daba Dw ~= 1,5e-6 en un emisor
                # apalancado: WACC 18,0% donde correspondía 12,6% (-34% de
                # valor de salida). No se adivina un factor de escala: se
                # declara inconsistente.
                best_facts = facts
                best_missing = ["capital_amounts_scale_mismatch"]
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

    def _annual_facts_by_year(
        self,
        db: Session,
        company: Company,
        metric: str,
    ) -> dict[int, FinancialFact]:
        """Latest annual fact per fiscal year (fiscal_quarter == 'FY')."""
        by_year: dict[int, FinancialFact] = {}
        for fact in self._facts_for_metric(db, company, metric):
            if fact.fiscal_year is None or fact.fiscal_quarter != "FY":
                continue
            if fact.fiscal_year not in by_year:
                by_year[fact.fiscal_year] = fact
        return by_year

    def _window_unavailable(
        self,
        db: Session,
        company: Company,
        metric: str,
        persist: bool,
        years_with_data: list[int],
        facts_used: list[FinancialFact],
    ) -> MetricResult:
        definition_version, formula, _, unit = METRIC_DEFINITIONS[metric]
        result = MetricResult(
            metric=metric,
            status="unavailable",
            period="unknown" if not years_with_data else f"FY{min(years_with_data)}-FY{max(years_with_data)}",
            value=None,
            unit=unit,
            definition_version=definition_version,
            formula=formula,
            numerator=None,
            denominator=None,
            source_fact_ids=[fact.id for fact in facts_used],
            calculation_trace={
                "reason": "insufficient_history",
                "coverage": f"{len(years_with_data)}/{WINDOW_MAX_YEARS}",
                "years_with_data": sorted(years_with_data),
                "minimum_years": WINDOW_MIN_YEARS,
            },
            confidence=Decimal("0.00"),
            fiscal_year=max(years_with_data) if years_with_data else None,
        )
        return self._persist_if_requested(db, company, result, persist)

    def _calculate_windowed_ratio(
        self,
        db: Session,
        company: Company,
        metric: str,
        persist: bool,
    ) -> MetricResult:
        definition_version, formula, _, unit = METRIC_DEFINITIONS[metric]
        numerator_metric, denominator_metric = WINDOWED_RATIO_METRICS[metric]
        numerators = self._annual_facts_by_year(db, company, numerator_metric)
        denominators = self._annual_facts_by_year(db, company, denominator_metric)
        usable_years = sorted(
            (
                year
                for year in set(numerators) & set(denominators)
                if Decimal(denominators[year].value) != 0
            ),
            reverse=True,
        )[:WINDOW_MAX_YEARS]
        facts_used = [f for year in usable_years for f in (numerators[year], denominators[year])]
        if len(usable_years) < WINDOW_MIN_YEARS:
            return self._window_unavailable(db, company, metric, persist, usable_years, facts_used)

        ratios = {
            year: Decimal(numerators[year].value) / Decimal(denominators[year].value)
            for year in usable_years
        }
        value = _quantize(sum(ratios.values()) / Decimal(len(ratios)))
        confidence = min(
            (Decimal(fact.confidence) for fact in facts_used),
            default=Decimal("0.70"),
        )
        result = MetricResult(
            metric=metric,
            status="ok",
            period=f"FY{min(usable_years)}-FY{max(usable_years)}",
            value=value,
            unit=unit,
            definition_version=definition_version,
            formula=formula,
            numerator=None,
            denominator=None,
            source_fact_ids=[fact.id for fact in facts_used],
            calculation_trace={
                "aggregation": "mean_of_annual_ratios",
                "coverage": f"{len(usable_years)}/{WINDOW_MAX_YEARS}",
                "years": sorted(usable_years),
                "ratios": {str(year): str(_quantize(ratio)) for year, ratio in ratios.items()},
                "inputs": {
                    str(year): {
                        "numerator_fact_id": numerators[year].id,
                        "numerator": str(numerators[year].value),
                        "denominator_fact_id": denominators[year].id,
                        "denominator": str(denominators[year].value),
                    }
                    for year in usable_years
                },
            },
            confidence=confidence,
            fiscal_year=max(usable_years),
        )
        return self._persist_if_requested(db, company, result, persist)

    def _calculate_windowed_composed(
        self,
        db: Session,
        company: Company,
        metric: str,
        persist: bool,
    ) -> MetricResult:
        definition_version, formula, inputs, unit = METRIC_DEFINITIONS[metric]
        facts_by_year = {
            input_metric: self._annual_facts_by_year(db, company, input_metric)
            for input_metric in inputs
        }
        common_years = set.intersection(
            *(set(facts) for facts in facts_by_year.values())
        )
        usable_years = sorted(common_years, reverse=True)[:WINDOW_MAX_YEARS]
        facts_used = [
            fact
            for year in usable_years
            for fact in (facts_by_year[input_metric][year] for input_metric in inputs)
        ]

        yearly: dict[int, Decimal] = {}
        skipped_zero_da: list[int] = []
        for year in usable_years:
            da = Decimal(facts_by_year["depreciation_amortization"][year].value)
            capex = abs(Decimal(facts_by_year["capital_expenditure"][year].value))
            if metric == "owner_earnings_5y":
                ni = Decimal(facts_by_year["net_income"][year].value)
                yearly[year] = ni + da - min(capex, da)
            else:  # capex_to_da_5y
                if da == 0:
                    skipped_zero_da.append(year)
                    continue
                yearly[year] = capex / da

        if len(yearly) < WINDOW_MIN_YEARS:
            return self._window_unavailable(
                db, company, metric, persist, sorted(yearly), facts_used
            )

        value = _quantize(sum(yearly.values()) / Decimal(len(yearly)))
        confidence = min(
            (Decimal(fact.confidence) for fact in facts_used),
            default=Decimal("0.70"),
        )
        years = sorted(yearly)
        result = MetricResult(
            metric=metric,
            status="ok",
            period=f"FY{min(years)}-FY{max(years)}",
            value=value,
            unit=unit,
            definition_version=definition_version,
            formula=formula,
            numerator=None,
            denominator=None,
            source_fact_ids=[fact.id for fact in facts_used],
            calculation_trace={
                "aggregation": "mean_of_annual_values",
                "coverage": f"{len(yearly)}/{WINDOW_MAX_YEARS}",
                "years": years,
                "values": {str(year): str(_quantize(v)) for year, v in yearly.items()},
                "skipped_zero_depreciation_years": skipped_zero_da,
                "inputs": {
                    str(year): {
                        f"{input_metric}_fact_id": facts_by_year[input_metric][year].id
                        for input_metric in inputs
                    }
                    for year in years
                },
            },
            confidence=confidence,
            fiscal_year=max(years),
        )
        return self._persist_if_requested(db, company, result, persist)

    def _latest_stored(self, db: Session, company: Company, metric: str) -> CalculatedMetric | None:
        return db.scalar(
            select(CalculatedMetric)
            .where(
                CalculatedMetric.company_id == company.id,
                CalculatedMetric.metric == metric,
            )
            .order_by(desc(CalculatedMetric.updated_at))
            .limit(1)
        )

    def _ratio_check(
        self,
        result: MetricResult,
        threshold: str,
        label: str,
    ) -> dict:
        threshold_value = Decimal(threshold)
        if result.status != "ok" or result.value is None:
            return {
                "check": label,
                "metric": result.metric,
                "threshold": threshold,
                "value": None,
                "passed": None,
                "reason": result.calculation_trace.get("reason", result.status),
            }
        return {
            "check": label,
            "metric": result.metric,
            "threshold": threshold,
            "value": str(result.value),
            "passed": result.value > threshold_value,
        }

    def _wacc_esef_equity_only(
        self, db: Session, company: Company
    ) -> tuple[Decimal, dict] | None:
        """WACC = coste de equity puro para emisores ESEF sin deuda desagregable.

        Aproximacion declarada (Nico, 25/9, documentada en /metodologia):
        como el coste de la deuda tras impuestos es inferior al coste del
        equity, el WACC todo-equity es una COTA SUPERIOR del WACC real -
        umbral conservador AL ALZA para los checks roic/cfroi > wacc.
        Solo se usa dentro de quality_moat_score_v2: el metric wacc
        almacenado no se toca.
        """
        rf_facts = self._facts_for_metric(db, company, "risk_free_rate")
        beta_facts = self._facts_for_metric(db, company, "beta")
        erp_facts = self._facts_for_metric(db, company, "equity_risk_premium")
        if not rf_facts or not beta_facts or not erp_facts:
            return None
        risk_free, _ = self._normalize_rate(rf_facts[0].value, allow_negative=True)
        erp, _ = self._normalize_rate(erp_facts[0].value)
        if risk_free is None or erp is None:
            return None
        beta = Decimal(beta_facts[0].value)
        country_rate = Decimal("0")
        crp_facts = self._facts_for_metric(db, company, "country_risk_premium")
        if crp_facts:
            normalized_crp, _ = self._normalize_rate(crp_facts[0].value)
            if normalized_crp is not None:
                country_rate = normalized_crp
        cost_of_equity = risk_free + beta * erp + country_rate
        fact_ids = [rf_facts[0].id, beta_facts[0].id, erp_facts[0].id]
        if crp_facts:
            fact_ids.append(crp_facts[0].id)
        trace = {
            "method": "wacc_esef_equity_only",
            "approximation": (
                "sin deuda ESEF desagregable (IFRS la reparte y la metodologia "
                "prohibe sumarla): WACC = coste de equity puro, cota superior "
                "del WACC real - umbral conservador al alza; aproximacion "
                "declarada por Nico 25/9, documentada en /metodologia"
            ),
            "cost_of_equity": str(cost_of_equity),
            "risk_free_rate": str(risk_free),
            "beta": str(beta),
            "equity_risk_premium": str(erp),
            "country_risk_premium": str(country_rate),
            "input_fact_ids": fact_ids,
        }
        return _quantize(cost_of_equity), trace

    def _roic_approx_esef(
        self, db: Session, company: Company
    ) -> tuple[Decimal, dict] | None:
        """ROIC aproximado para emisores ESEF sin desglose de deuda.

        Hueco IFRS honesto: borrowings current/noncurrent/lease van repartidos
        y la metodologia prohibe sumarlos (ver ESEF_METRIC_MAP). Aproximacion
        declarada (Nico, 25/9, documentada en /metodologia): capital invertido
        ~ total_assets - cash_and_equivalents. Como activos - caja >= deuda +
        equity - caja, el denominador se sobreestima y el ROIC queda
        conservador A LA BAJA: nunca infla el check roic_gt_wacc.
        """
        assets = self._annual_facts_by_year(db, company, "total_assets")
        cash = self._annual_facts_by_year(db, company, "cash_and_equivalents")
        operating = self._annual_facts_by_year(db, company, "operating_income")
        common = sorted(set(assets) & set(cash) & set(operating), reverse=True)
        if not common:
            return None
        year = common[0]
        tax_rate, tax_trace, _ = self._tax_rate_for_period(
            db, company, operating[year], allow_fallback=True
        )
        if tax_rate is None:
            return None
        nopat = Decimal(operating[year].value) * (Decimal("1") - tax_rate)
        invested = Decimal(assets[year].value) - Decimal(cash[year].value)
        prior_invested = None
        basis = "current_period"
        prior_years = [y for y in common if y < year]
        if prior_years:
            py = prior_years[0]
            prior_invested = Decimal(assets[py].value) - Decimal(cash[py].value)
            invested = (invested + prior_invested) / Decimal("2")
            basis = "average_current_and_prior_period"
        if invested <= 0:
            return None
        trace = {
            "method": "roic_approx_esef_assets_menos_caja",
            "approximation": (
                "capital invertido aproximado como total_assets - cash_and_equivalents "
                "(>= deuda + equity - caja: ROIC conservador a la baja); "
                "aproximacion declarada por Nico 25/9, documentada en /metodologia"
            ),
            "fiscal_year": year,
            **tax_trace,
            "nopat": str(nopat),
            "invested_capital": str(invested),
            "invested_capital_basis": basis,
            "prior_invested_capital": (
                str(prior_invested) if prior_invested is not None else None
            ),
        }
        return _quantize(nopat / invested), trace

    def _base_quality_checks(
        self,
        db: Session,
        company: Company,
        persist: bool,
    ) -> tuple[list[dict], list[MetricResult]]:
        fcf_result = self._calculate_windowed_ratio(db, company, "fcf_margin_5y", persist)
        net_margin_result = self._calculate_windowed_ratio(db, company, "net_margin_5y", persist)
        roe_result = self._calculate_windowed_ratio(db, company, "roe_5y", persist)
        roa_result = self._calculate_windowed_ratio(db, company, "roa_5y", persist)

        checks = [
            self._ratio_check(fcf_result, "0.05", "fcf_margin_5y_gt_5pct"),
            self._ratio_check(net_margin_result, "0.15", "net_margin_5y_gt_15pct"),
            self._ratio_check(roe_result, "0.15", "roe_5y_gt_15pct"),
            self._ratio_check(roa_result, "0.07", "roa_5y_gt_7pct"),
        ]

        roic_result = self.calculate(db, company, "roic", persist=persist)
        wacc_result = self.calculate(db, company, "wacc", persist=persist)
        if roic_result.status == "ok" and wacc_result.status == "ok":
            checks.append(
                {
                    "check": "roic_gt_wacc",
                    "metric": "roic",
                    "threshold": str(wacc_result.value),
                    "value": str(roic_result.value),
                    "passed": roic_result.value > wacc_result.value,
                }
            )
        else:
            checks.append(
                {
                    "check": "roic_gt_wacc",
                    "metric": "roic",
                    "threshold": str(wacc_result.value) if wacc_result.value is not None else None,
                    "value": str(roic_result.value) if roic_result.value is not None else None,
                    "passed": None,
                    "reason": "roic_or_wacc_unavailable",
                }
            )

        component_results = [
            fcf_result,
            net_margin_result,
            roe_result,
            roa_result,
            roic_result,
            wacc_result,
        ]
        return checks, component_results

    def _quality_score_result(
        self,
        db: Session,
        company: Company,
        persist: bool,
        metric: str,
        framework_label: str,
        checks: list[dict],
        component_results: list[MetricResult],
    ) -> MetricResult:
        definition_version, formula, _, unit = METRIC_DEFINITIONS[metric]
        evaluable = [check for check in checks if check["passed"] is not None]
        score = sum(1 for check in checks if check["passed"] is True)
        if not evaluable:
            status = "unavailable"
            value = None
        elif len(evaluable) == len(checks):
            status = "ok"
            value = Decimal(score)
        else:
            status = "partial"
            value = Decimal(score)
        periods = [r.period for r in component_results if r.period and r.period != "unknown"]
        result = MetricResult(
            metric=metric,
            status=status,
            period=periods[0] if periods else "unknown",
            value=value,
            unit=unit,
            definition_version=definition_version,
            formula=formula,
            numerator=None,
            denominator=None,
            source_fact_ids=sorted(
                {fact_id for r in component_results for fact_id in r.source_fact_ids}
            ),
            calculation_trace={
                "framework": framework_label,
                "checks": checks,
                "checks_evaluable": len(evaluable),
                "checks_total": len(checks),
                "score": score,
            },
            confidence=min(
                (r.confidence for r in component_results if r.status == "ok"),
                default=Decimal("0.00"),
            ),
            fiscal_year=next(
                (r.fiscal_year for r in component_results if r.fiscal_year is not None),
                None,
            ),
        )
        return self._persist_if_requested(db, company, result, persist)

    def _calculate_quality_score(
        self,
        db: Session,
        company: Company,
        persist: bool,
    ) -> MetricResult:
        checks, component_results = self._base_quality_checks(db, company, persist)
        return self._quality_score_result(
            db,
            company,
            persist,
            "quality_moat_score",
            "MARCO_NICO_V1 (apuntes manuscritos de Nico, sept 2026)",
            checks,
            component_results,
        )

    def _calculate_quality_score_v2(
        self,
        db: Session,
        company: Company,
        persist: bool,
    ) -> MetricResult:
        checks, component_results = self._base_quality_checks(db, company, persist)

        # Aproximaciones declaradas ESEF (Nico, 25/9, documentadas en
        # /metodologia): IFRS reparte la deuda (borrowings current/noncurrent/
        # lease) y la metodologia prohibe sumarla, asi que el ROIC estandar y
        # el WACC estandar no son calculables para emisores ESEF. Ambas
        # aproximaciones son conservadoras CONTRA el check: WACC = coste de
        # equity puro (cota superior del umbral) y capital invertido =
        # activos - caja (cota superior del denominador, ROIC a la baja).
        esef_wacc = None
        if company.currency == "EUR":
            esef_wacc = self._wacc_esef_equity_only(db, company)
            if esef_wacc is not None:
                wacc_value, wacc_trace = esef_wacc
                roic_approx = self._roic_approx_esef(db, company)
                for i, check in enumerate(checks):
                    if check["check"] != "roic_gt_wacc" or check["passed"] is not None:
                        continue
                    if roic_approx is None:
                        continue
                    roic_value, roic_trace = roic_approx
                    checks[i] = {
                        "check": "roic_gt_wacc",
                        "metric": "roic",
                        "threshold": str(wacc_value),
                        "value": str(roic_value),
                        "passed": roic_value > wacc_value,
                        "approximation": {
                            "roic": roic_trace,
                            "wacc": wacc_trace,
                        },
                    }

        # CFROI (aproximacion declarada) por encima del coste de capital:
        # creacion de valor en terminos de caja, no solo contables.
        cfroi_result = self.calculate(db, company, "cfroi_approx", persist=persist)
        wacc_result = component_results[-1]
        if cfroi_result.status == "ok" and wacc_result.status == "ok":
            checks.append(
                {
                    "check": "cfroi_approx_gt_wacc",
                    "metric": "cfroi_approx",
                    "threshold": str(wacc_result.value),
                    "value": str(cfroi_result.value),
                    "passed": cfroi_result.value > wacc_result.value,
                }
            )
        elif esef_wacc is not None and cfroi_result.status == "ok":
            wacc_value, wacc_trace = esef_wacc
            checks.append(
                {
                    "check": "cfroi_approx_gt_wacc",
                    "metric": "cfroi_approx",
                    "threshold": str(wacc_value),
                    "value": str(cfroi_result.value),
                    "passed": cfroi_result.value > wacc_value,
                    "approximation": {"wacc": wacc_trace},
                }
            )
        else:
            checks.append(
                {
                    "check": "cfroi_approx_gt_wacc",
                    "metric": "cfroi_approx",
                    "threshold": str(wacc_result.value) if wacc_result.value is not None else None,
                    "value": str(cfroi_result.value) if cfroi_result.value is not None else None,
                    "passed": None,
                    "reason": "cfroi_approx_or_wacc_unavailable",
                }
            )
        component_results.append(cfroi_result)

        # Owner earnings (Buffett): la media de hasta 5 anos debe ser
        # positiva; un negocio que no genera caja para el dueno tras
        # mantenimiento no tiene foso economico.
        oe_result = self._calculate_windowed_composed(db, company, "owner_earnings_5y", persist)
        checks.append(self._ratio_check(oe_result, str(V2_OWNER_EARNINGS_MIN), "owner_earnings_5y_positive"))
        component_results.append(oe_result)

        # Disciplina de capital: |capex|/D&A medio <= 1.5 (1.0 = solo
        # mantenimiento). Mas arriba, el negocio exige reinversion pesada
        # continua - el foso queda en duda. Umbral <=, no <.
        capex_da_result = self._calculate_windowed_composed(db, company, "capex_to_da_5y", persist)
        if capex_da_result.status == "ok" and capex_da_result.value is not None:
            checks.append(
                {
                    "check": "capex_to_da_5y_le_150pct",
                    "metric": "capex_to_da_5y",
                    "threshold": str(V2_CAPEX_TO_DA_MAX),
                    "value": str(capex_da_result.value),
                    "passed": capex_da_result.value <= V2_CAPEX_TO_DA_MAX,
                }
            )
        else:
            checks.append(
                {
                    "check": "capex_to_da_5y_le_150pct",
                    "metric": "capex_to_da_5y",
                    "threshold": str(V2_CAPEX_TO_DA_MAX),
                    "value": None,
                    "passed": None,
                    "reason": capex_da_result.calculation_trace.get("reason", capex_da_result.status),
                }
            )
        component_results.append(capex_da_result)

        return self._quality_score_result(
            db,
            company,
            persist,
            "quality_moat_score_v2",
            "MARCO_NICO_V2 (V1 + cfroi/owner earnings/capex; umbrales delegados por Nico 2026-09-25)",
            checks,
            component_results,
        )

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
        if result.status in {"ok", "partial"}:
            # Higiene: una fila con valor real sustituye a las filas
            # unavailable de ciclos anteriores con otro periodo (incluida la
            # "unknown" de los recalculos sin historia); sin esto la tabla
            # crece x2 en cada ciclo (la UI lee la mas reciente por
            # updated_at, pero la basura se acumula).
            db.execute(
                delete(CalculatedMetric).where(
                    CalculatedMetric.company_id == company.id,
                    CalculatedMetric.metric == result.metric,
                    CalculatedMetric.period != result.period,
                    CalculatedMetric.status == "unavailable",
                    CalculatedMetric.definition_version == result.definition_version,
                )
            )
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
