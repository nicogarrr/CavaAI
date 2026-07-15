from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import (
    Company,
    DecisionJournalEntry,
    ExpectationReview,
    FinancialFact,
    FundamentalForecast,
    FundamentalModelVersion,
    MarketPrice,
    ThesisVersion,
)


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
        model = db.scalar(
            select(FundamentalModelVersion)
            .where(FundamentalModelVersion.company_id == company.id)
            .order_by(desc(FundamentalModelVersion.version))
            .limit(1)
        )
        if not model:
            return []
        forecasts = list(
            db.scalars(
                select(FundamentalForecast)
                .where(
                    FundamentalForecast.model_version_id == model.id,
                    FundamentalForecast.scenario == "base",
                )
                .order_by(
                    FundamentalForecast.fiscal_year,
                    FundamentalForecast.metric,
                )
            ).all()
        )
        reviews: list[ExpectationReview] = []
        for forecast in forecasts:
            actual = db.scalar(
                select(FinancialFact)
                .where(
                    FinancialFact.company_id == company.id,
                    FinancialFact.metric == forecast.metric,
                    FinancialFact.fiscal_year == forecast.fiscal_year,
                )
                .order_by(desc(FinancialFact.created_at))
                .limit(1)
            )
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
                    status="pending_actual",
                )
                db.add(review)

            if actual is None:
                review.status = "pending_actual"
                review.actual_fact_id = None
                review.actual_value = None
                review.variance = None
                review.variance_percent = None
            else:
                actual_value = Decimal(actual.value)
                variance = actual_value - forecast.value
                variance_percent = (
                    variance / abs(forecast.value)
                    if forecast.value != 0
                    else None
                )
                review.actual_fact_id = actual.id
                review.actual_value = actual_value
                review.variance = variance
                review.variance_percent = variance_percent
                if variance_percent is None or abs(variance_percent) <= Decimal("0.05"):
                    review.status = "met"
                elif variance_percent > 0:
                    review.status = "beat"
                else:
                    review.status = "miss"
                review.trace = {
                    "threshold": "5_percent",
                    "actual_source_type": actual.source_type,
                    "actual_period": actual.period,
                }
            review.reviewed_at = datetime.now(UTC)
            reviews.append(review)
        db.commit()
        for review in reviews:
            db.refresh(review)
        return reviews

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
