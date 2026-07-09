from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import CalculatedMetric, Company, FinancialFact


MetricFormula = tuple[str, str, tuple[str, ...], str]

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
        "ROIC_STANDARD_V1",
        "NOPAT / invested_capital, where NOPAT = operating_income * (1 - 0.21) and invested_capital = total_debt + total_equity - cash_and_equivalents",
        ("operating_income", "total_debt", "total_equity", "cash_and_equivalents"),
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
        facts = self._coherent_facts(db, company, inputs)
        missing_inputs = [input_metric for input_metric in inputs if input_metric not in facts]
        period = self._period_for_result(facts)

        if missing_inputs:
            return MetricResult(
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
                    "reason": "missing_inputs",
                    "missing_inputs": missing_inputs,
                    "available_inputs": sorted(facts),
                },
                confidence=Decimal("0.00"),
            )

        numerator, denominator, trace = self._evaluate(metric, facts)
        if denominator is None or denominator == 0 or numerator is None:
            return MetricResult(
                metric=metric,
                status="unavailable",
                period=period,
                value=None,
                unit=unit,
                definition_version=definition_version,
                formula=formula,
                numerator=numerator,
                denominator=denominator,
                source_fact_ids=[fact.id for fact in facts.values()],
                calculation_trace={
                    **trace,
                    "reason": "zero_or_invalid_denominator",
                },
                confidence=Decimal("0.00"),
                fiscal_year=next(iter(facts.values())).fiscal_year if facts else None,
                fiscal_quarter=next(iter(facts.values())).fiscal_quarter if facts else None,
            )

        value = _quantize(numerator / denominator)
        confidence = min((Decimal(fact.confidence) for fact in facts.values()), default=Decimal("0.70"))
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
            source_fact_ids=[fact.id for fact in facts.values()],
            calculation_trace={
                **trace,
                "inputs": {
                    input_metric: {
                        "fact_id": fact.id,
                        "value": str(fact.value),
                        "period": fact.period,
                        "source_type": fact.source_type,
                    }
                    for input_metric, fact in facts.items()
                },
            },
            confidence=confidence,
            fiscal_year=next(iter(facts.values())).fiscal_year if facts else None,
            fiscal_quarter=next(iter(facts.values())).fiscal_quarter if facts else None,
        )

        if persist:
            stored = self._upsert(db, company, result)
            result.id = stored.id
        return result

    def latest_calculated(self, db: Session, company: Company) -> list[CalculatedMetric]:
        return list(
            db.scalars(
                select(CalculatedMetric)
                .where(CalculatedMetric.company_id == company.id)
                .order_by(CalculatedMetric.metric, desc(CalculatedMetric.updated_at))
            ).all()
        )

    def _coherent_facts(self, db: Session, company: Company, inputs: tuple[str, ...]) -> dict[str, FinancialFact]:
        anchors = self._facts_for_metric(db, company, inputs[0])
        for anchor in anchors:
            facts = {inputs[0]: anchor}
            for metric in inputs[1:]:
                match = self._match_fact(db, company, metric, anchor)
                if match:
                    facts[metric] = match
            if len(facts) == len(inputs):
                return facts
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
            if candidate.fiscal_year == anchor.fiscal_year and candidate.fiscal_quarter == anchor.fiscal_quarter:
                return candidate
        return None

    def _period_for_result(self, facts: dict[str, FinancialFact]) -> str:
        if not facts:
            return "unknown"
        first = next(iter(facts.values()))
        return first.period

    def _evaluate(self, metric: str, facts: dict[str, FinancialFact]) -> tuple[Decimal | None, Decimal | None, dict]:
        value = lambda key: Decimal(facts[key].value)
        if metric == "roic":
            tax_rate = Decimal("0.21")
            nopat = value("operating_income") * (Decimal("1") - tax_rate)
            invested_capital = value("total_debt") + value("total_equity") - value("cash_and_equivalents")
            return nopat, invested_capital, {
                "method": "standard_roic",
                "tax_rate": str(tax_rate),
                "nopat": str(nopat),
                "invested_capital": str(invested_capital),
            }
        numerator_key, denominator_key = METRIC_DEFINITIONS[metric][2]
        return value(numerator_key), value(denominator_key), {
            "method": "simple_ratio",
            "numerator_metric": numerator_key,
            "denominator_metric": denominator_key,
        }

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
