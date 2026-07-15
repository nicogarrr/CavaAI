from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import (
    CalculatedMetric,
    Company,
    DecisionJournalEntry,
    ExpectationReview,
    FinancialFact,
    FundamentalForecast,
    FundamentalModelVersion,
    MarketPrice,
    ThesisVersion,
)
from app.services.metric_semantics import MetricSemanticsRegistry


class DecisionJournalService:
    def create(
        self,
        db: Session,
        company: Company,
        *,
        decision: str,
        rationale: str,
        what_must_be_true: list[str],
    ) -> DecisionJournalEntry:
        thesis = db.scalar(
            select(ThesisVersion)
            .where(ThesisVersion.company_id == company.id)
            .order_by(desc(ThesisVersion.version))
            .limit(1)
        )
        model = db.scalar(
            select(FundamentalModelVersion)
            .where(FundamentalModelVersion.company_id == company.id)
            .order_by(desc(FundamentalModelVersion.version))
            .limit(1)
        )
        price = db.scalar(
            select(MarketPrice)
            .where(MarketPrice.company_id == company.id)
            .order_by(desc(MarketPrice.date))
            .limit(1)
        )
        entry = DecisionJournalEntry(
            company_id=company.id,
            thesis_version_id=thesis.id if thesis else None,
            model_version_id=model.id if model else None,
            decision=decision,
            rationale=rationale,
            what_must_be_true=what_must_be_true,
            price=price.close if price else None,
            metadata_={
                "thesis_version": thesis.version if thesis else None,
                "model_version": model.version if model else None,
            },
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry

    def list(self, db: Session, company: Company) -> list[DecisionJournalEntry]:
        return list(
            db.scalars(
                select(DecisionJournalEntry)
                .where(DecisionJournalEntry.company_id == company.id)
                .order_by(
                    desc(DecisionJournalEntry.decision_date),
                    desc(DecisionJournalEntry.id),
                )
            ).all()
        )


class ExpectationRealityService:
    def review(self, db: Session, company: Company) -> list[ExpectationReview]:
        rows = list(
            db.execute(
                select(FundamentalForecast, FundamentalModelVersion)
                .join(
                    FundamentalModelVersion,
                    FundamentalModelVersion.id == FundamentalForecast.model_version_id,
                )
                .where(
                    FundamentalModelVersion.company_id == company.id,
                    FundamentalForecast.scenario == "base",
                )
                .order_by(
                    FundamentalForecast.fiscal_year,
                    FundamentalForecast.metric,
                    FundamentalModelVersion.created_at,
                )
            ).all()
        )
        grouped: dict[
            tuple[int, str], list[tuple[FundamentalForecast, FundamentalModelVersion]]
        ] = {}
        for forecast, model in rows:
            grouped.setdefault((forecast.fiscal_year, forecast.metric), []).append(
                (forecast, model)
            )
        reviews: list[ExpectationReview] = []
        for (fiscal_year, metric), candidates in grouped.items():
            actual_fact = db.scalar(
                select(FinancialFact)
                .where(
                    FinancialFact.company_id == company.id,
                    FinancialFact.metric == metric,
                    FinancialFact.fiscal_year == fiscal_year,
                )
                .order_by(desc(FinancialFact.created_at))
                .limit(1)
            )
            actual_metric = db.scalar(
                select(CalculatedMetric)
                .where(
                    CalculatedMetric.company_id == company.id,
                    CalculatedMetric.metric == metric,
                    CalculatedMetric.fiscal_year == fiscal_year,
                    CalculatedMetric.value.is_not(None),
                )
                .order_by(desc(CalculatedMetric.created_at))
                .limit(1)
            )
            actual = self._preferred_actual(actual_fact, actual_metric)
            actual_created_at = actual.created_at if actual is not None else None
            eligible = [
                item
                for item in candidates
                if actual_created_at is None
                or self._is_before(item[1].created_at, actual_created_at)
            ]
            if not eligible:
                # A model created after the result is known is not a forecast.
                continue
            forecast, model = eligible[-1]
            review = db.scalar(
                select(ExpectationReview).where(
                    ExpectationReview.forecast_id == forecast.id
                )
            )
            if review is None:
                review = ExpectationReview(
                    company_id=company.id,
                    model_version_id=model.id,
                    forecast_id=forecast.id,
                    fiscal_year=forecast.fiscal_year,
                    metric=forecast.metric,
                    expected_value=forecast.value,
                    semantics=MetricSemanticsRegistry.get(metric).direction,
                    status="pending_actual",
                )
                db.add(review)

            if actual is None:
                review.status = "pending_actual"
                review.actual_fact_id = None
                review.actual_metric_id = None
                review.actual_source_type = None
                review.actual_value = None
                review.variance = None
                review.variance_percent = None
            else:
                actual_value = Decimal(actual.value)
                variance = actual_value - forecast.value
                status, variance_percent = MetricSemanticsRegistry.classify(
                    metric, forecast.value, actual_value
                )
                is_calculated = isinstance(actual, CalculatedMetric)
                review.actual_fact_id = None if is_calculated else actual.id
                review.actual_metric_id = actual.id if is_calculated else None
                review.actual_source_type = (
                    "calculated_metric" if is_calculated else "financial_fact"
                )
                review.actual_value = actual_value
                review.variance = variance
                review.variance_percent = variance_percent
                rule = MetricSemanticsRegistry.get(metric)
                review.semantics = rule.direction
                review.status = status
                review.trace = {
                    "tolerance": str(rule.tolerance),
                    "semantics": rule.direction,
                    "actual_source_type": (
                        "calculated_metric"
                        if is_calculated
                        else actual.source_type
                    ),
                    "actual_period": actual.period,
                    "selection_policy": "latest model created before actual",
                    "forecast_model_created_at": model.created_at.isoformat(),
                    "actual_created_at": actual.created_at.isoformat(),
                }
            review.reviewed_at = datetime.now(UTC)
            reviews.append(review)
        db.commit()
        for review in reviews:
            db.refresh(review)
        return reviews

    @staticmethod
    def _preferred_actual(
        fact: FinancialFact | None,
        metric: CalculatedMetric | None,
    ) -> FinancialFact | CalculatedMetric | None:
        if fact is None:
            return metric
        if metric is None:
            return fact
        # Raw reported observations win ties; otherwise use the newest canonical value.
        return fact if fact.created_at >= metric.created_at else metric

    @staticmethod
    def _is_before(model_time: datetime, actual_time: datetime) -> bool:
        model_value = model_time.replace(tzinfo=None)
        actual_value = actual_time.replace(tzinfo=None)
        return model_value < actual_value

    def list(self, db: Session, company: Company) -> list[ExpectationReview]:
        return list(
            db.scalars(
                select(ExpectationReview)
                .where(ExpectationReview.company_id == company.id)
                .order_by(
                    desc(ExpectationReview.fiscal_year),
                    ExpectationReview.metric,
                )
            ).all()
        )
