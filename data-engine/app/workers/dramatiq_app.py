from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from typing import Any

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from app.core.config import get_settings

settings = get_settings()
broker = RedisBroker(url=settings.redis_url)
dramatiq.set_broker(broker)


def _failure(actor: str, exc: Exception, **context: Any) -> dict[str, Any]:
    return {
        "status": "error",
        "actor": actor,
        "error": {
            "type": type(exc).__name__,
            "message": str(exc),
            "context": context,
        },
    }


def _batch_status(processed: int, errors: list[dict]) -> str:
    if errors and processed:
        return "partial"
    if errors:
        return "error"
    return "ok"


def _run(coroutine):
    return asyncio.run(coroutine)


def _session(tenant_id: int | None, user_id: str | None):
    from app.core.database import SessionLocal
    from app.models import Tenant

    if tenant_id is None or not user_id:
        raise ValueError("tenant_id and user_id are required for background jobs")
    db = SessionLocal()
    tenant = db.get(Tenant, tenant_id)
    if tenant is None or tenant.status != "active":
        db.close()
        raise ValueError(f"Active tenant {tenant_id} was not found")
    db.info["tenant_id"] = tenant.id
    db.info["user_id"] = user_id
    return db


def tenant_contexts() -> list[tuple[int, str]]:
    """Return explicit tenant/user pairs for scheduler fan-out."""
    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models import Tenant

    with SessionLocal() as db:
        tenants = db.scalars(
            select(Tenant)
            .where(Tenant.status == "active")
            .execution_options(include_all_tenants=True)
            .order_by(Tenant.id)
        ).all()
        contexts: list[tuple[int, str]] = []
        for tenant in tenants:
            user_id = str((tenant.metadata_ or {}).get("created_by") or "").strip()
            if user_id:
                contexts.append((tenant.id, user_id))
        return contexts


def _companies(db, ticker: str | None = None):
    from sqlalchemy import select

    from app.models import Company

    statement = select(Company)
    if ticker:
        statement = statement.where(Company.ticker == ticker.upper())
    return list(db.scalars(statement.order_by(Company.ticker)).all())


def _rollback(db) -> None:
    try:
        db.rollback()
    except Exception:
        pass


def _message_id(message) -> str | None:
    return str(message.message_id) if getattr(message, "message_id", None) else None


@dramatiq.actor(max_retries=2, min_backoff=15_000)
def refresh_sec_filings(
    tenant_id: int | None = None,
    user_id: str | None = None,
    ticker: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    actor_name = "refresh_sec_filings"
    try:
        from app.services.feed_ingestion_service import FeedIngestionService

        db = _session(tenant_id, user_id)
        try:
            service = FeedIngestionService()
            processed = ingested = queued_documents = 0
            errors: list[dict] = []
            for company in _companies(db, ticker):
                if not company.cik:
                    continue
                try:
                    result = _run(
                        service.poll_sec(
                            company.cik,
                            ticker=company.ticker,
                            limit=limit,
                        )
                    )
                    if result.errors:
                        errors.extend(
                            {"ticker": company.ticker, "source": "sec", "message": error}
                            for error in result.errors
                        )
                    ingestion = service.ingest_news_result(
                        db,
                        result,
                        ticker=company.ticker,
                    )
                    if result.status != "error":
                        processed += 1
                    ingested += int(ingestion.get("created", 0))
                    for item in result.items:
                        if not item.url:
                            continue
                        process_document.send(
                            company.ticker,
                            item.title,
                            item.url,
                            "SEC",
                            item.published_at.isoformat() if item.published_at else None,
                            tenant_id,
                            user_id,
                        )
                        queued_documents += 1
                except Exception as exc:
                    _rollback(db)
                    errors.append(
                        {
                            "ticker": company.ticker,
                            "source": "sec",
                            "type": type(exc).__name__,
                            "message": str(exc),
                        }
                    )
            return {
                "status": _batch_status(processed, errors),
                "actor": actor_name,
                "companies_processed": processed,
                "news_ingested": ingested,
                "documents_queued": queued_documents,
                "errors": errors,
            }
        finally:
            db.close()
    except Exception as exc:
        return _failure(actor_name, exc, tenant_id=tenant_id, user_id=user_id, ticker=ticker, limit=limit)


@dramatiq.actor(max_retries=2, min_backoff=15_000)
def refresh_ir_pages(
    tenant_id: int | None = None,
    user_id: str | None = None,
    ticker: str | None = None,
) -> dict[str, Any]:
    actor_name = "refresh_ir_pages"
    try:
        from app.services.feed_ingestion_service import FeedIngestionService

        db = _session(tenant_id, user_id)
        try:
            service = FeedIngestionService()
            processed = ingested = queued_documents = 0
            errors: list[dict] = []
            for company in _companies(db, ticker):
                if not company.ir_url:
                    continue
                try:
                    result = _run(
                        service.poll_ir(company.ir_url, ticker=company.ticker)
                    )
                    if result.errors:
                        errors.extend(
                            {"ticker": company.ticker, "source": "ir", "message": error}
                            for error in result.errors
                        )
                    ingestion = service.ingest_news_result(
                        db,
                        result,
                        ticker=company.ticker,
                    )
                    if result.status != "error":
                        processed += 1
                    ingested += int(ingestion.get("created", 0))
                    for item in result.items:
                        if not item.url:
                            continue
                        process_document.send(
                            company.ticker,
                            item.title,
                            item.url,
                            "IR",
                            item.published_at.isoformat() if item.published_at else None,
                            tenant_id,
                            user_id,
                        )
                        queued_documents += 1
                except Exception as exc:
                    _rollback(db)
                    errors.append(
                        {
                            "ticker": company.ticker,
                            "source": "ir",
                            "type": type(exc).__name__,
                            "message": str(exc),
                        }
                    )
            return {
                "status": _batch_status(processed, errors),
                "actor": actor_name,
                "companies_processed": processed,
                "news_ingested": ingested,
                "documents_queued": queued_documents,
                "errors": errors,
            }
        finally:
            db.close()
    except Exception as exc:
        return _failure(actor_name, exc, tenant_id=tenant_id, user_id=user_id, ticker=ticker)


@dramatiq.actor(max_retries=2, min_backoff=15_000)
def refresh_rss_feeds(
    tenant_id: int | None = None,
    user_id: str | None = None,
    feed_url: str | None = None,
    ticker: str | None = None,
) -> dict[str, Any]:
    actor_name = "refresh_rss_feeds"
    try:
        from app.services.feed_ingestion_service import (
            FeedIngestionService,
            RSSFeed,
            configured_rss_feeds,
        )

        feeds = [RSSFeed(feed_url, ticker.upper() if ticker else None)] if feed_url else configured_rss_feeds()
        if not feeds:
            return {
                "status": "skipped",
                "actor": actor_name,
                "reason": "RSS_FEEDS is empty",
                "feeds_processed": 0,
            }

        db = _session(tenant_id, user_id)
        try:
            service = FeedIngestionService()
            processed = ingested = 0
            errors: list[dict] = []
            for feed in feeds:
                try:
                    result = _run(
                        service.poll_rss(feed.url, ticker=feed.ticker)
                    )
                    if result.errors:
                        errors.extend(
                            {"url": feed.url, "source": "rss", "message": error}
                            for error in result.errors
                        )
                    ingestion = service.ingest_news_result(
                        db,
                        result,
                        ticker=feed.ticker,
                    )
                    if result.status != "error":
                        processed += 1
                    ingested += int(ingestion.get("created", 0))
                except Exception as exc:
                    _rollback(db)
                    errors.append(
                        {
                            "url": feed.url,
                            "source": "rss",
                            "type": type(exc).__name__,
                            "message": str(exc),
                        }
                    )
            return {
                "status": _batch_status(processed, errors),
                "actor": actor_name,
                "feeds_processed": processed,
                "news_ingested": ingested,
                "errors": errors,
            }
        finally:
            db.close()
    except Exception as exc:
        return _failure(
            actor_name,
            exc,
            tenant_id=tenant_id,
            user_id=user_id,
            feed_url=feed_url,
            ticker=ticker,
        )


@dramatiq.actor(max_retries=2, min_backoff=15_000)
def refresh_news(
    tenant_id: int | None = None,
    user_id: str | None = None,
    ticker: str | None = None,
    max_records: int = 25,
) -> dict[str, Any]:
    actor_name = "refresh_news"
    try:
        from app.services.feed_ingestion_service import FeedIngestionService

        db = _session(tenant_id, user_id)
        try:
            service = FeedIngestionService()
            processed = ingested = 0
            errors: list[dict] = []
            for company in _companies(db, ticker):
                try:
                    query = f'"{company.name}" OR {company.ticker}'
                    result = _run(
                        service.poll_gdelt(
                            query,
                            ticker=company.ticker,
                            max_records=max_records,
                        )
                    )
                    if result.errors:
                        errors.extend(
                            {"ticker": company.ticker, "source": "gdelt", "message": error}
                            for error in result.errors
                        )
                    ingestion = service.ingest_news_result(
                        db,
                        result,
                        ticker=company.ticker,
                    )
                    if result.status != "error":
                        processed += 1
                    ingested += int(ingestion.get("created", 0))
                except Exception as exc:
                    _rollback(db)
                    errors.append(
                        {
                            "ticker": company.ticker,
                            "source": "gdelt",
                            "type": type(exc).__name__,
                            "message": str(exc),
                        }
                    )
            return {
                "status": _batch_status(processed, errors),
                "actor": actor_name,
                "companies_processed": processed,
                "news_ingested": ingested,
                "errors": errors,
            }
        finally:
            db.close()
    except Exception as exc:
        return _failure(
            actor_name,
            exc,
            tenant_id=tenant_id,
            user_id=user_id,
            ticker=ticker,
            max_records=max_records,
        )


@dramatiq.actor(max_retries=3, min_backoff=30_000)
def process_document(
    ticker: str,
    title: str,
    url: str,
    source_type: str,
    published_at: str | None = None,
    tenant_id: int | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    actor_name = "process_document"
    try:
        from app.services.feed_ingestion_service import FeedIngestionService

        published = (
            datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            if published_at
            else None
        )
        db = _session(tenant_id, user_id)
        try:
            result = _run(
                FeedIngestionService().ingest_document_url(
                    db,
                    ticker=ticker,
                    title=title,
                    url=url,
                    source_type=source_type,
                    published_at=published,
                )
            )
            return {"status": result.get("status", "ok"), "actor": actor_name, "result": result}
        finally:
            db.close()
    except Exception as exc:
        return _failure(
            actor_name,
            exc,
            tenant_id=tenant_id,
            user_id=user_id,
            ticker=ticker,
            url=url,
            source_type=source_type,
        )


@dramatiq.actor(max_retries=1)
def consolidate_memory(
    tenant_id: int | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    actor_name = "consolidate_memory"
    try:
        from sqlalchemy import select

        from app.models import MemoryItem

        db = _session(tenant_id, user_id)
        try:
            items = list(
                db.scalars(
                    select(MemoryItem)
                    .where(MemoryItem.status == "active")
                    .order_by(MemoryItem.id)
                ).all()
            )
            canonical: dict[tuple, Any] = {}
            merged = 0
            for item in items:
                normalized = re.sub(r"\s+", " ", item.content.strip().lower())
                key = (item.company_id, item.scope, item.memory_type, normalized)
                existing = canonical.get(key)
                if existing is None:
                    canonical[key] = item
                    continue
                existing.importance = max(existing.importance, item.importance)
                existing.metadata_ = {
                    **(existing.metadata_ or {}),
                    "last_consolidated_at": datetime.now(UTC).isoformat(),
                }
                item.status = "consolidated"
                item.metadata_ = {
                    **(item.metadata_ or {}),
                    "consolidated_into": existing.id,
                }
                merged += 1
            db.commit()
            return {
                "status": "ok",
                "actor": actor_name,
                "active_scanned": len(items),
                "duplicates_consolidated": merged,
            }
        finally:
            db.close()
    except Exception as exc:
        return _failure(actor_name, exc, tenant_id=tenant_id, user_id=user_id)


@dramatiq.actor(max_retries=1)
def scan_contradictions(
    tenant_id: int | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    actor_name = "scan_contradictions"
    try:
        from sqlalchemy import select

        from app.models import Claim, ClaimEvidence, ThesisChange
        from app.services.thesis_change_types import claim_change_type

        db = _session(tenant_id, user_id)
        try:
            evidence = list(
                db.scalars(
                    select(ClaimEvidence).where(
                        ClaimEvidence.evidence_type == "contradicts"
                    )
                ).all()
            )
            claim_ids = {item.claim_id for item in evidence}
            claims = (
                list(db.scalars(select(Claim).where(Claim.id.in_(claim_ids))).all())
                if claim_ids
                else []
            )
            existing_changes = list(
                db.scalars(
                    select(ThesisChange).where(
                        ThesisChange.change_type
                        == claim_change_type("contradicted")
                    )
                ).all()
            )
            already_flagged = {
                claim_id
                for change in existing_changes
                for claim_id in (change.affected_claim_ids or [])
            }
            created = 0
            for claim in claims:
                claim.status = "contradicted"
                claim.last_reviewed_at = datetime.now(UTC)
                if claim.id in already_flagged:
                    continue
                db.add(
                    ThesisChange(
                        company_id=claim.company_id,
                        from_version_id=claim.thesis_version_id,
                        to_version_id=claim.thesis_version_id,
                        change_type=claim_change_type("contradicted"),
                        impact_direction="negative",
                        materiality_score=claim.materiality_score,
                        summary=f"Contradictory evidence found for claim: {claim.statement[:220]}",
                        affected_claim_ids=[claim.id],
                        affected_metrics=[],
                        requires_review=True,
                    )
                )
                created += 1
            db.commit()
            return {
                "status": "ok",
                "actor": actor_name,
                "contradictory_evidence": len(evidence),
                "claims_flagged": len(claims),
                "changes_created": created,
            }
        finally:
            db.close()
    except Exception as exc:
        return _failure(actor_name, exc, tenant_id=tenant_id, user_id=user_id)


@dramatiq.actor(max_retries=1)
def review_theses(
    tenant_id: int | None = None,
    user_id: str | None = None,
    ticker: str | None = None,
) -> dict[str, Any]:
    actor_name = "review_theses"
    try:
        from sqlalchemy import select

        from app.models import Company, ThesisChange
        from app.services.thesis_service import ThesisService

        db = _session(tenant_id, user_id)
        try:
            pending = list(
                db.scalars(
                    select(ThesisChange).where(ThesisChange.requires_review.is_(True))
                ).all()
            )
            company_ids = {change.company_id for change in pending if change.company_id}
            statement = select(Company)
            if ticker:
                statement = statement.where(Company.ticker == ticker.upper())
            elif company_ids:
                statement = statement.where(Company.id.in_(company_ids))
            else:
                return {
                    "status": "ok",
                    "actor": actor_name,
                    "companies_reviewed": 0,
                    "pending_changes": 0,
                    "reviews": [],
                }

            service = ThesisService()
            reviews: list[dict] = []
            errors: list[dict] = []
            for company in db.scalars(statement.order_by(Company.ticker)).all():
                try:
                    thesis = service.generate(db, company.ticker, force_new_version=False)
                    resolved = 0
                    for change in pending:
                        if change.company_id != company.id:
                            continue
                        thesis_created_at = thesis.created_at
                        change_created_at = change.created_at
                        if thesis_created_at and thesis_created_at.tzinfo is None:
                            thesis_created_at = thesis_created_at.replace(tzinfo=UTC)
                        if change_created_at and change_created_at.tzinfo is None:
                            change_created_at = change_created_at.replace(tzinfo=UTC)
                        thesis_is_newer = bool(
                            thesis_created_at
                            and change_created_at
                            and thesis_created_at >= change_created_at
                        )
                        if change.from_version_id != thesis.id and thesis_is_newer:
                            change.to_version_id = thesis.id
                            change.requires_review = False
                            resolved += 1
                    db.commit()
                    reviews.append(
                        {
                            "ticker": company.ticker,
                            "thesis_id": thesis.id,
                            "version": thesis.version,
                            "status": thesis.status,
                            "changes_resolved": resolved,
                        }
                    )
                except Exception as exc:
                    _rollback(db)
                    errors.append(
                        {
                            "ticker": company.ticker,
                            "type": type(exc).__name__,
                            "message": str(exc),
                        }
                    )
            return {
                "status": _batch_status(len(reviews), errors),
                "actor": actor_name,
                "companies_reviewed": len(reviews),
                "pending_changes": len(pending),
                "reviews": reviews,
                "errors": errors,
            }
        finally:
            db.close()
    except Exception as exc:
        return _failure(actor_name, exc, tenant_id=tenant_id, user_id=user_id, ticker=ticker)


@dramatiq.actor(max_retries=1)
def run_daily_research() -> dict[str, Any]:
    actor_name = "run_daily_research"
    jobs: list[tuple[str, Any]] = [
        ("sec_refresh", refresh_sec_filings),
        ("ir_refresh", refresh_ir_pages),
        ("rss_refresh", refresh_rss_feeds),
        ("news_refresh", refresh_news),
        ("memory_consolidation", consolidate_memory),
        ("contradiction_scan", scan_contradictions),
        ("thesis_review", review_theses),
    ]
    queued: list[dict] = []
    errors: list[dict] = []
    contexts = tenant_contexts()
    for tenant_id, user_id in contexts:
        for job_name, actor in jobs:
            try:
                message = actor.send(tenant_id, user_id)
                queued.append(
                    {
                        "job": job_name,
                        "tenant_id": tenant_id,
                        "user_id": user_id,
                        "message_id": _message_id(message),
                    }
                )
            except Exception as exc:
                errors.append(
                    {
                        "job": job_name,
                        "tenant_id": tenant_id,
                        "user_id": user_id,
                        "type": type(exc).__name__,
                        "message": str(exc),
                    }
                )
    return {
        "status": _batch_status(len(queued), errors),
        "actor": actor_name,
        "workflow": "DailyResearchWorkflow",
        "queued": queued,
        "errors": errors,
    }


# Short aliases keep operational imports stable while actor names remain descriptive.
refresh_sec = refresh_sec_filings
refresh_ir = refresh_ir_pages
refresh_rss = refresh_rss_feeds


if __name__ == "__main__":
    print("Dramatiq actors registered. Run with: dramatiq app.workers.dramatiq_app")
