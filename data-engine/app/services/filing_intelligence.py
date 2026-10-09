"""Tenant-bound filing changes and earnings excerpts in the existing document store."""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from urllib.parse import quote, urlsplit

from sqlalchemy import desc, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Company, Document, DocumentChunk, Position, ResearchAlert, ThesisVersion, WatchItem
from app.services.company_resolver import resolve_company
from app.services.earnings_releases import summarize_release
from app.services.filing_changes import comparable, compare_sections, reported_period
from app.services.notification_service import record_in_app_delivery

VERSION = "filing-intelligence-v1"
KEY = "filing_intelligence"
MAX_CHUNKS = 2000


def official_document(document: Document) -> bool:
    try:
        url = urlsplit(document.source_url or "")
    except ValueError:
        return False
    return (url.scheme == "https" and not url.username and not url.password
            and ((url.hostname in {"www.sec.gov", "sec.gov"} and url.path.startswith("/Archives/edgar/data/"))
                 or url.hostname in {"www.cnmv.es", "cnmv.es"})
            and document.source_type.lower() in {"sec", "cnmv", "primary_official", "esef"})


def _chunks(db: Session, document: Document) -> list[dict] | None:
    rows = db.scalars(select(DocumentChunk).where(
        DocumentChunk.tenant_id == document.tenant_id, DocumentChunk.document_id == document.id,
    ).order_by(DocumentChunk.chunk_index).limit(MAX_CHUNKS + 1)).all()
    if len(rows) > MAX_CHUNKS:
        return None
    return [{"id": row.id, "chunk_index": row.chunk_index, "text": row.text} for row in rows]


def _citation(document: Document) -> dict:
    return {"document_id": document.id, "url": document.source_url, "checksum": document.checksum,
            "published_at": document.published_at.isoformat() if document.published_at else None,
            "reported_period": (reported_period(document.metadata_ or {}).isoformat()
                                if reported_period(document.metadata_ or {}) else None)}


def analyze_document(db: Session, document: Document) -> dict:
    """No commit, network calls or LLM. Caller owns transaction and retries."""
    tenant = db.info.get("tenant_id")
    if tenant is None or tenant != document.tenant_id:
        raise ValueError("Tenant context required for filing analysis")
    if not official_document(document):
        return {"status": "insufficient_data", "reason": "Sin documento SEC/CNMV con URL oficial."}
    company = db.get(Company, document.company_id) if document.company_id else None
    chunks = _chunks(db, document)
    meta = document.metadata_ or {}
    result = {"version": VERSION, "source": _citation(document)}
    if not chunks:
        if company:
            _alert(db, company, document, {"source": _citation(document)}, event_type="new_filing")
        result["status"] = "insufficient_data"
        result["reason"] = "Sin texto completo disponible dentro del límite de análisis."
        document.metadata_ = {**meta, KEY: result}
        db.flush()
        return result
    form = meta.get("form")
    if form == "8-K" or (str(form).startswith("EX-99") and meta.get("parent_form") == "8-K"):
        result["earnings"] = summarize_release(chunks, meta)
        result["status"] = result["earnings"]["status"]
    else:
        prior = None
        # SQL bounds by declared period year, not ingestion date; no arbitrary
        # latest-N window can starve a valid year-ago report after re-ingestion.
        period = reported_period(meta)
        if period and form in {"10-K", "10-Q", "20-F", "40-F", "annual_report"}:
            candidates = db.scalars(select(Document).where(
                Document.tenant_id == tenant, Document.company_id == document.company_id,
                Document.id != document.id,
                Document.metadata_["form"].as_string() == form,
                or_(Document.metadata_["report_date"].as_string().like(f"{period.year - 1}-%"),
                    Document.metadata_["period_of_report"].as_string().like(f"{period.year - 1}-%")),
            ).order_by(desc(Document.published_at), desc(Document.id)))
            for candidate in candidates:
                if official_document(candidate) and comparable(meta, candidate.metadata_ or {}):
                    prior = candidate
                    break
        before = _chunks(db, prior) if prior else None
        if prior is None or not before:
            result["status"] = "insufficient_data"
            result["reason"] = "Sin informe comparable del mismo periodo del año anterior."
        else:
            result["previous_source"] = _citation(prior)
            result["diff"] = compare_sections(chunks, before)
            result["status"] = result["diff"]["status"]
    company = db.get(Company, document.company_id) if document.company_id else None
    thesis = db.scalar(select(ThesisVersion).where(
        ThesisVersion.tenant_id == tenant, ThesisVersion.company_id == document.company_id,
    ).order_by(desc(ThesisVersion.version)).limit(1)) if company else None
    result["thesis_version_id"] = thesis.id if thesis else None
    result["thesis_path"] = f"/research/{quote(company.ticker, safe='')}" if company else None
    # Metadata replacement is required for SQLAlchemy JSON dirty tracking.
    document.metadata_ = {**meta, KEY: result}
    db.flush()
    if company:
        _alert(db, company, document, result,
               event_type=None if result["status"] in {"changed", "ready"} else "new_filing")
    return result


def _alert(db: Session, company: Company, document: Document, result: dict, *, event_type: str | None = None) -> None:
    tenant = db.info["tenant_id"]
    held = db.scalar(select(Position.id).where(
        Position.tenant_id == tenant, Position.company_id == company.id, Position.quantity > 0,
    ).limit(1))
    symbols = db.scalars(select(WatchItem.symbol).where(WatchItem.tenant_id == tenant)).all()
    watched = any((resolved := resolve_company(db, symbol)) is not None and resolved.id == company.id
                  for symbol in symbols)
    if held is None and not watched:
        return
    fingerprint = hashlib.sha256(
        f"{VERSION}|{tenant}|{company.id}|{document.source_url}|{document.checksum}".encode()
    ).hexdigest()
    if db.scalar(select(ResearchAlert.id).where(
        ResearchAlert.tenant_id == tenant, ResearchAlert.fingerprint == fingerprint,
    )) is not None:
        return
    earnings = "earnings" in result
    title = f"{company.ticker}: {'comunicado de resultados' if earnings else 'cambios en el informe'}"
    message = ("Comunicado de resultados disponible con citas originales." if earnings else
               "Cambios textuales frente al mismo periodo del año anterior. No implican por sí solos materialidad financiera.")
    if event_type == "new_filing":
        title = f"Documento oficial nuevo: {company.ticker}"
        message = "Documento SEC/CNMV disponible. El análisis puede estar pendiente o sin datos; revisa la fuente antes de cambiar la tesis."
    try:
        with db.begin_nested():
            alert = ResearchAlert(
                tenant_id=tenant, company_id=company.id, severity="medium", status="open",
                alert_type=event_type or ("earnings_release" if earnings else "filing_changes"), title=title,
                message=message, fingerprint=fingerprint, channels=["in_app"],
                last_triggered_at=datetime.now(UTC),
                metadata_={**result, "document_id": document.id, "source_url": document.source_url,
                           "matching": (["cartera"] if held is not None else []) + (["watchlist"] if watched else [])},
            )
            db.add(alert)
            db.flush()
            record_in_app_delivery(db, alert)
    except IntegrityError:
        # Only suppress the unique-fingerprint race, not another integrity bug.
        if db.scalar(select(ResearchAlert.id).where(
            ResearchAlert.tenant_id == tenant, ResearchAlert.fingerprint == fingerprint,
        )) is None:
            raise
