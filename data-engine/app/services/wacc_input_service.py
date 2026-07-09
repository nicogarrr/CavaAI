from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Company, Document, FinancialFact
from app.services.connectors.fred import FREDClient


class WaccInputService:
    """Refresh dated, sourced market assumptions used by WACC_STANDARD_V1."""

    async def refresh(self, db: Session, company: Company) -> dict:
        settings = get_settings()
        as_of = datetime.now(UTC).date().isoformat()
        facts: list[FinancialFact] = []
        sources: list[int] = []

        fred = FREDClient()
        if fred.configured():
            payload = await fred.series(
                getattr(settings, "wacc_risk_free_series", "DGS10"),
                limit=10,
            )
            observation = next(
                (
                    item
                    for item in payload.get("observations", [])
                    if item.get("value") not in {None, "."}
                ),
                None,
            )
            if observation:
                risk_free_date = str(observation.get("date") or as_of)
                risk_free = self._decimal(observation.get("value"))
                if risk_free is not None:
                    risk_free /= Decimal("100")
                    document = self._source_document(
                        db,
                        company,
                        source_type="FRED",
                        title=(
                            f"FRED {getattr(settings, 'wacc_risk_free_series', 'DGS10')} "
                            f"{risk_free_date}"
                        ),
                        metadata={
                            "series": getattr(
                                settings, "wacc_risk_free_series", "DGS10"
                            ),
                            "date": risk_free_date,
                            "currency": company.currency,
                        },
                    )
                    sources.append(document.id)
                    facts.append(
                        self._upsert_fact(
                            db,
                            company,
                            metric="risk_free_rate",
                            value=risk_free,
                            period=risk_free_date,
                            source=document,
                            source_type="FRED",
                            confidence=Decimal("0.98"),
                        )
                    )

        policy_document = self._source_document(
            db,
            company,
            source_type="wacc_policy",
            title=f"WACC policy assumptions {as_of}",
            metadata={
                "methodology": "WACC_POLICY_V1",
                "date": as_of,
                "currency": company.currency,
                "country": getattr(
                    settings, "wacc_default_country", "US"
                ),
            },
        )
        sources.append(policy_document.id)
        for metric, value in [
            (
                "equity_risk_premium",
                Decimal(
                    str(
                        getattr(
                            settings,
                            "wacc_equity_risk_premium",
                            0.0433,
                        )
                    )
                ),
            ),
            (
                "country_risk_premium",
                Decimal(
                    str(
                        getattr(
                            settings,
                            "wacc_country_risk_premium",
                            0.0,
                        )
                    )
                ),
            ),
        ]:
            facts.append(
                self._upsert_fact(
                    db,
                    company,
                    metric=metric,
                    value=value,
                    period=as_of,
                    source=policy_document,
                    source_type="wacc_policy",
                    confidence=Decimal("0.70"),
                )
            )
        db.commit()
        return {
            "status": "refreshed",
            "ticker": company.ticker,
            "as_of": as_of,
            "currency": company.currency,
            "fact_ids": [fact.id for fact in facts],
            "source_document_ids": sorted(set(sources)),
            "missing": [
                metric
                for metric in ["risk_free_rate", "beta", "market_cap"]
                if db.scalar(
                    select(FinancialFact.id)
                    .where(
                        FinancialFact.company_id == company.id,
                        FinancialFact.metric == metric,
                    )
                    .limit(1)
                )
                is None
            ],
        }

    def _source_document(
        self,
        db: Session,
        company: Company,
        *,
        source_type: str,
        title: str,
        metadata: dict,
    ) -> Document:
        document = db.scalar(
            select(Document).where(
                Document.company_id == company.id,
                Document.source_type == source_type,
                Document.title == title,
            )
        )
        if document is None:
            document = Document(
                company_id=company.id,
                title=title,
                source_type=source_type,
                published_at=datetime.now(UTC),
                metadata_=metadata,
            )
            db.add(document)
            db.flush()
        return document

    def _upsert_fact(
        self,
        db: Session,
        company: Company,
        *,
        metric: str,
        value: Decimal,
        period: str,
        source: Document,
        source_type: str,
        confidence: Decimal,
    ) -> FinancialFact:
        fact = db.scalar(
            select(FinancialFact).where(
                FinancialFact.company_id == company.id,
                FinancialFact.metric == metric,
                FinancialFact.period == period,
                FinancialFact.source_type == source_type,
            )
        )
        if fact is None:
            fact = FinancialFact(
                company_id=company.id,
                metric=metric,
                value=value,
                unit="decimal",
                period=period,
                source_id=source.id,
                source_type=source_type,
                is_reported=True,
                is_adjusted=False,
                confidence=confidence,
            )
            db.add(fact)
            db.flush()
        else:
            fact.value = value
            fact.source_id = source.id
            fact.confidence = confidence
        return fact

    def _decimal(self, value) -> Decimal | None:
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
