from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm import LLMRequest, Message, ResponseFormat, parse_json_response
from app.llm.base import LLMProvider
from app.llm.factory import create_llm_provider
from app.models import (
    Company,
    CompanyKPI,
    Document,
    DocumentChunk,
    FinancialFact,
    KPIExtractionCandidate,
)
from app.services.company_framework import resolve_company_framework
from app.services.budget import BudgetController, BudgetExceededError
from app.services.langfuse_client import LangfuseTracer


PROMPT_VERSION = "company-kpi-extraction-v1"
RATE_KEYS = {
    "penetration", "revenue_share", "utilization", "take_rate", "churn",
    "retention", "backlog_conversion", "fee_rate", "cash_yield", "occupancy",
    "royalty_rate", "premium_growth", "return_on_tangible_equity", "roe",
    "combined_ratio", "net_interest_margin", "cet1_ratio", "organic_growth",
}
COUNT_MARKERS = (
    "accounts", "subscribers", "customers", "seats", "launches", "satellites",
    "units", "agreements", "trips",
)
MONEY_KEYS = {
    "revenue", "tpv", "arr", "aum", "backlog", "asset_value", "nav",
    "holdco_debt", "earned_premiums", "investment_income", "net_operating_income",
    "tangible_book_value", "book_value",
}


def _key(value: str) -> str:
    return (
        value.strip().lower().replace("&", "and").replace("/", "_")
        .replace("-", "_").replace(" ", "_")
    )


class CompanyKPIRegistryService:
    def sync(
        self, db: Session, company: Company, *, commit: bool = True
    ) -> list[CompanyKPI]:
        framework = resolve_company_framework(company)
        revenue = {_key(item) for item in framework.revenue_drivers}
        required = {_key(item) for item in framework.required_fact_metrics}
        labels = list(
            dict.fromkeys(
                framework.revenue_drivers
                + framework.kpis
                + framework.required_fact_metrics
            )
        )
        rows: list[CompanyKPI] = []
        active_keys: set[str] = set()
        for label in labels:
            metric_key = _key(label)
            active_keys.add(metric_key)
            row = db.scalar(
                select(CompanyKPI).where(
                    CompanyKPI.company_id == company.id,
                    CompanyKPI.metric_key == metric_key,
                )
            )
            if row is None:
                row = CompanyKPI(company_id=company.id, metric_key=metric_key)
                db.add(row)
            row.display_name = label.replace("_", " ").strip().title()
            row.aliases = list(
                dict.fromkeys(
                    [label, label.replace("_", " "), metric_key, metric_key.upper()]
                )
            )
            row.canonical_unit = self._unit(metric_key, company.currency)
            row.driver_type = "revenue_driver" if metric_key in revenue else "kpi"
            row.required = metric_key in required
            row.active = True
            row.registry_version = f"{framework.key}-v1"
            row.metadata_ = {
                "framework": framework.key,
                "formula_role": row.driver_type,
                "approval_policy": "human_approval_required",
            }
            rows.append(row)
        existing = db.scalars(
            select(CompanyKPI).where(CompanyKPI.company_id == company.id)
        ).all()
        for row in existing:
            if row.metric_key not in active_keys:
                row.active = False
        db.flush()
        if commit:
            db.commit()
            for row in rows:
                db.refresh(row)
        return rows

    @staticmethod
    def _unit(metric: str, currency: str) -> str:
        if metric in RATE_KEYS or metric.endswith(("_margin", "_rate", "_ratio")):
            return "decimal"
        if metric in MONEY_KEYS:
            return currency
        if any(marker in metric for marker in COUNT_MARKERS):
            return "count"
        if metric.startswith("price") or metric.endswith(("_price", "_arpu")):
            return f"{currency}_per_unit"
        return "unknown"


class KPIExtractionService:
    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.provider = provider or create_llm_provider()

    async def extract_document(
        self,
        db: Session,
        document: Document,
        *,
        commit: bool = True,
    ) -> list[KPIExtractionCandidate]:
        if document.company_id is None:
            raise ValueError("KPI extraction requires a company-specific document")
        company = db.get(Company, document.company_id)
        if company is None:
            raise ValueError("Document company no longer exists")
        registry = CompanyKPIRegistryService().sync(db, company, commit=False)
        chunks = list(
            db.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == document.id)
                .order_by(DocumentChunk.chunk_index)
                .limit(30)
            ).all()
        )
        if not chunks:
            return []
        chunk_map = {chunk.id: chunk for chunk in chunks}
        source_text = "\n\n".join(
            f"[chunk:{chunk.id}]\n{chunk.text}" for chunk in chunks
        )[:30000]
        metric_keys = [row.metric_key for row in registry if row.active]
        schema = self._schema(metric_keys)
        budget = BudgetController()
        if not budget.can_spend(db, 0.02):
            raise BudgetExceededError("LLM budget exhausted")
        request = LLMRequest(
                messages=[
                    Message(
                        "system",
                        "Extract only explicitly reported company KPIs. Do not infer, calculate "
                        "or estimate missing values. The quote must be verbatim and chunk_id must "
                        "identify the supplied chunk. Return no observation when period or value "
                        "is ambiguous.",
                    ),
                    Message(
                        "user",
                        json.dumps(
                            {
                                "company": {"ticker": company.ticker, "name": company.name},
                                "registry": [
                                    {
                                        "metric_key": row.metric_key,
                                        "aliases": row.aliases,
                                        "canonical_unit": row.canonical_unit,
                                        "required": row.required,
                                    }
                                    for row in registry
                                ],
                                "document": {
                                    "id": document.id,
                                    "title": document.title,
                                    "source_type": document.source_type,
                                },
                                "chunks": source_text,
                            },
                            ensure_ascii=False,
                        ),
                    ),
                ],
                task="kpi_extraction",
                temperature=0,
                max_tokens=2500,
                response_format=ResponseFormat.json_schema(
                    schema, name="company_kpi_observations", strict=True
                ),
                metadata={"prompt_version": PROMPT_VERSION},
            )
        with LangfuseTracer().workflow(
            "CompanyKPIExtraction",
            {
                "workflow": "company_kpi_extraction",
                "prompt_version": PROMPT_VERSION,
                "retrieval_set": [f"document_chunk:{chunk.id}" for chunk in chunks],
                "tools": [],
                "escalation": False,
            },
        ) as llm_trace:
            try:
                response = await self.provider.complete(request)
                payload = parse_json_response(response.text)
                cost = budget.estimate_cost_eur(
                    response.model,
                    response.usage.input_tokens,
                    response.usage.output_tokens,
                )
                budget.record(
                    db,
                    response.model,
                    "company_kpi_extraction",
                    cost,
                    response.usage.total_tokens,
                    commit=False,
                )
                if not isinstance(payload, dict) or not isinstance(payload.get("observations"), list):
                    raise ValueError("Invalid KPI extraction response")
                confidence_values = [
                    float(item.get("confidence") or 0)
                    for item in payload["observations"]
                    if isinstance(item, dict)
                ]
                llm_trace.update(
                    model=response.model,
                    provider=response.provider,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    cache_read_tokens=response.usage.cache_read_tokens,
                    cache_write_tokens=response.usage.cache_write_tokens,
                    cost=cost,
                    citations=len(payload["observations"]),
                    json_validity=True,
                    fallback=False,
                    evaluation_score=(
                        sum(confidence_values) / len(confidence_values)
                        if confidence_values
                        else 1.0
                    ),
                )
                llm_trace.output = {
                    "observations": len(payload["observations"]),
                    "json_validity": True,
                }
            except Exception as exc:
                llm_trace.update(
                    provider=getattr(self.provider, "name", "unknown"),
                    json_validity=False,
                    fallback=False,
                    error=type(exc).__name__,
                )
                raise
        registry_by_key = {row.metric_key: row for row in registry}
        created: list[KPIExtractionCandidate] = []
        for observation in payload["observations"]:
            if not isinstance(observation, dict):
                continue
            metric_key = str(observation.get("metric_key") or "")
            kpi = registry_by_key.get(metric_key)
            chunk_id = self._integer(observation.get("chunk_id"))
            chunk = chunk_map.get(chunk_id)
            if kpi is None or chunk is None:
                continue
            quote = str(observation.get("quote") or "").strip()
            locator_valid = bool(quote) and self._contains_quote(chunk.text, quote)
            raw_value = str(observation.get("raw_value") or "").strip()
            raw_unit = str(observation.get("raw_unit") or "unknown").strip()
            normalized, normalization_trace = self._normalize(
                raw_value, raw_unit, kpi.canonical_unit
            )
            fiscal_year = self._integer(observation.get("fiscal_year"))
            fiscal_quarter = str(observation.get("fiscal_quarter") or "FY").upper()
            period = str(observation.get("period") or "").strip() or (
                f"{fiscal_quarter}{fiscal_year}" if fiscal_year else "unknown"
            )
            period_valid = fiscal_quarter in {"Q1", "Q2", "Q3", "Q4", "FY"} and fiscal_year is not None
            reconciliation = (
                "reconciled"
                if locator_valid and normalized is not None and period_valid
                else "needs_review"
            )
            status = "pending_approval" if reconciliation == "reconciled" else "needs_review"
            existing = db.scalar(
                select(KPIExtractionCandidate).where(
                    KPIExtractionCandidate.document_id == document.id,
                    KPIExtractionCandidate.document_chunk_id == chunk.id,
                    KPIExtractionCandidate.metric_key == metric_key,
                    KPIExtractionCandidate.period == period,
                    KPIExtractionCandidate.raw_value == raw_value,
                )
            )
            if existing is not None:
                created.append(existing)
                continue
            confidence = max(0.0, min(1.0, float(observation.get("confidence") or 0)))
            candidate = KPIExtractionCandidate(
                company_id=company.id,
                company_kpi_id=kpi.id,
                document_id=document.id,
                document_chunk_id=chunk.id,
                metric_key=metric_key,
                raw_label=str(observation.get("raw_label") or metric_key)[:240],
                raw_value=raw_value[:160],
                raw_unit=raw_unit[:80],
                normalized_value=normalized,
                canonical_unit=kpi.canonical_unit,
                period=period[:40],
                fiscal_year=fiscal_year,
                fiscal_quarter=fiscal_quarter if period_valid else None,
                source_locator={"chunk_id": chunk.id, "quote": quote},
                reconciliation_status=reconciliation,
                status=status,
                confidence=Decimal(str(confidence)),
                extraction_model=response.model,
                prompt_version=PROMPT_VERSION,
                trace={
                    "provider": response.provider,
                    "request_id": response.request_id,
                    "locator_verified": locator_valid,
                    "period_valid": period_valid,
                    "normalization": normalization_trace,
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
            )
            db.add(candidate)
            created.append(candidate)
        db.flush()
        if commit:
            db.commit()
            for candidate in created:
                db.refresh(candidate)
        return created

    def approve(
        self,
        db: Session,
        candidate: KPIExtractionCandidate,
        *,
        actor: str,
    ) -> FinancialFact:
        if candidate.status != "pending_approval" or candidate.normalized_value is None:
            raise ValueError("Only reconciled pending candidates can be approved")
        document = db.get(Document, candidate.document_id)
        if document is None:
            raise ValueError("Source document no longer exists")
        fact = db.scalar(
            select(FinancialFact).where(
                FinancialFact.company_id == candidate.company_id,
                FinancialFact.metric == candidate.metric_key,
                FinancialFact.period == candidate.period,
                FinancialFact.source_id == candidate.document_id,
            )
        )
        if fact is None:
            fact = FinancialFact(
                company_id=candidate.company_id,
                metric=candidate.metric_key,
                value=candidate.normalized_value,
                unit=candidate.canonical_unit,
                period=candidate.period,
                fiscal_year=candidate.fiscal_year,
                fiscal_quarter=candidate.fiscal_quarter,
                source_id=candidate.document_id,
                source_type=document.source_type,
                is_reported=True,
                is_adjusted=False,
                confidence=candidate.confidence,
            )
            db.add(fact)
            db.flush()
        candidate.status = "approved"
        candidate.approved_by = actor
        candidate.approved_at = datetime.now(UTC)
        candidate.canonical_fact_id = fact.id
        db.commit()
        db.refresh(fact)
        return fact

    @staticmethod
    def reject(db: Session, candidate: KPIExtractionCandidate, *, actor: str) -> None:
        if candidate.status == "approved":
            raise ValueError("Approved observations cannot be rejected")
        candidate.status = "rejected"
        candidate.approved_by = actor
        candidate.approved_at = datetime.now(UTC)
        db.commit()

    @staticmethod
    def _normalize(
        raw_value: str, raw_unit: str, canonical_unit: str
    ) -> tuple[Decimal | None, dict[str, Any]]:
        compact = raw_value.strip().replace(",", "")
        negative = compact.startswith("(") and compact.endswith(")")
        compact = compact.strip("()")
        match = re.search(r"[-+]?\d+(?:\.\d+)?", compact)
        if not match:
            return None, {"status": "invalid_number", "raw_value": raw_value}
        try:
            value = Decimal(match.group(0))
        except InvalidOperation:
            return None, {"status": "invalid_number", "raw_value": raw_value}
        if negative:
            value = -abs(value)
        unit_text = f"{raw_value} {raw_unit}".lower()
        multiplier = Decimal("1")
        if re.search(r"\b(billion|bn|b)\b", unit_text):
            multiplier = Decimal("1000000000")
        elif re.search(r"\b(million|mn|mm|m)\b", unit_text):
            multiplier = Decimal("1000000")
        elif re.search(r"\b(thousand|k)\b", unit_text):
            multiplier = Decimal("1000")
        value *= multiplier
        percent = "%" in unit_text or "percent" in unit_text
        if canonical_unit == "decimal" and percent:
            value /= Decimal("100")
        return value, {
            "status": "normalized",
            "multiplier": str(multiplier),
            "percent_to_decimal": canonical_unit == "decimal" and percent,
        }

    @staticmethod
    def _contains_quote(text: str, quote: str) -> bool:
        normalize = lambda value: " ".join(value.lower().split())
        return normalize(quote) in normalize(text)

    @staticmethod
    def _integer(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _schema(metric_keys: list[str]) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "observations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "metric_key": {"type": "string", "enum": metric_keys},
                            "raw_label": {"type": "string"},
                            "raw_value": {"type": "string"},
                            "raw_unit": {"type": "string"},
                            "period": {"type": "string"},
                            "fiscal_year": {"type": "integer"},
                            "fiscal_quarter": {"type": "string", "enum": ["Q1", "Q2", "Q3", "Q4", "FY"]},
                            "chunk_id": {"type": "integer"},
                            "quote": {"type": "string"},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        },
                        "required": [
                            "metric_key", "raw_label", "raw_value", "raw_unit",
                            "period", "fiscal_year", "fiscal_quarter", "chunk_id",
                            "quote", "confidence",
                        ],
                    },
                }
            },
            "required": ["observations"],
        }
