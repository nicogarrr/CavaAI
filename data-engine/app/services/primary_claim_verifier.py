"""Strict comparison of atomic claims with located official ITU fields.

No model inference, headline matching, or numeric overlap is verification.
Callers must supply a field, exact proposed value, and literal source excerpt.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document, DocumentChunk, NewsEvent, PrimarySourceRecord
from app.services.itu_record_parser import FIELDS


@dataclass(frozen=True)
class AtomicClaim:
    fieldname: str
    value: str
    literal: str


def _literal_has_value(literal: str, value: str) -> bool:
    # Preserve the exact value as an independently delimited atom; "344"
    # inside "1344" cannot be treated as an explicit claim of 344.
    return bool(value and re.search(rf"(?<![\w.]){re.escape(value)}(?![\w.])", literal, re.UNICODE))


def _unverified(claim: AtomicClaim, reason: str) -> dict:
    return {"fieldname": claim.fieldname, "claimed_value": claim.value,
            "claim_literal": claim.literal, "status": "not_verifiable",
            "reason": reason, "evidence": None}


def verify_itu_claims(db: Session, *, news_event_id: int,
                      claims: list[AtomicClaim]) -> list[dict]:
    """Compare only parsed, complete fields of a tenant-linked ITU record.

    A caller's claim is data, never trusted proof. A primary record without a
    parsed field or with conflicting revisions yields no verdict. Official
    receipt/registry dates never masquerade as publication dates.
    """
    tenant_id = db.info.get("tenant_id")
    if tenant_id is None:
        raise ValueError("Tenant context required")
    if len(claims) > 20 or any(not isinstance(c, AtomicClaim) or len(c.literal) > 1000
                              or len(c.value) > 250 or len(c.fieldname) > 100 for c in claims):
        raise ValueError("Atomic claim input exceeds bounds")
    news = db.scalar(select(NewsEvent).where(NewsEvent.id == news_event_id,
                                               NewsEvent.tenant_id == tenant_id))
    if news is None or news.company_id is None:
        raise LookupError("Tenant-scoped news event not found")
    records = db.scalars(select(PrimarySourceRecord).where(
        PrimarySourceRecord.tenant_id == tenant_id,
        PrimarySourceRecord.news_event_id == news.id,
    ).order_by(PrimarySourceRecord.id)).all()
    # Cross-version disagreement is not silently settled by a newest-row pick.
    documents = []
    invalid_revision = False
    for record in records:
        doc = db.scalar(select(Document).where(Document.id == record.document_id,
                                                Document.tenant_id == tenant_id,
                                                Document.company_id == news.company_id,
                                                Document.source_type == "primary_official"))
        if (doc is not None and doc.checksum == record.checksum and
                doc.source_url == record.final_url and
                urlsplit(doc.source_url).path.startswith("/ITU-R/space/asreceived/Publication/DisplayPublication/")):
            documents.append((record, doc))
        else:
            invalid_revision = True
    out = []
    source_headline = (news.metadata_ or {}).get("source_headline")
    for claim in claims:
        # The only original publisher text this pipeline retains is the
        # connector headline. Do not accept caller-created claim literals or
        # convert a semantic statement ("approved 344 satellites") into a
        # narrower field claim by spotting the number 344.
        canonical = f"{FIELDS[claim.fieldname]}: {claim.value}" if claim.fieldname in FIELDS else ""
        if invalid_revision:
            out.append(_unverified(claim, "Linked official revision failed provenance validation"))
            continue
        if (not isinstance(source_headline, str) or claim.literal != source_headline
                or claim.literal.strip() != canonical or not claim.value
                or not _literal_has_value(claim.literal, claim.value)):
            out.append(_unverified(claim, "Exact attributed field claim not available in original headline"))
            continue
        matching = []
        for record, doc in documents:
            chunks = db.scalars(select(DocumentChunk).where(
                DocumentChunk.document_id == doc.id,
                DocumentChunk.tenant_id == tenant_id,
            ).order_by(DocumentChunk.chunk_index)).all()
            for chunk in chunks:
                actual_chunk_hash = hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()
                if (chunk.metadata_.get("checksum") != doc.checksum or
                        chunk.metadata_.get("chunk_sha256") != actual_chunk_hash):
                    invalid_revision = True
                    continue
                blocks = chunk.metadata_.get("block_metadata", [])
                for block in blocks:
                    if (not isinstance(block, dict) or block.get("fieldname") != claim.fieldname
                            or block.get("field_complete") is not True
                            or block.get("format") != "itu_asreceived"):
                        continue
                    submission = (doc.metadata_ or {}).get("itu_record", {}).get("submission_id")
                    locator = f"form[Item.SubmissionId={submission}] [data-fieldname={claim.fieldname}]@data-value"
                    if block.get("locator") != locator:
                        continue
                    text_match = re.search(rf"(?:^|\n){re.escape(FIELDS[claim.fieldname])}: ([^\n]+)", chunk.text)
                    if not text_match:
                        continue
                    official_value = text_match.group(1).strip()
                    if not official_value:
                        continue
                    matching.append((official_value, record, doc, chunk, locator))
        if invalid_revision or not matching or len({value for value, *_ in matching}) != 1:
            out.append(_unverified(claim, "Official field unavailable, invalid, or conflicting versions"))
            continue
        official_value, record, doc, chunk, locator = matching[-1]
        status = "supported" if claim.value == official_value else "contradicted"
        extracted = f"{FIELDS[claim.fieldname]}: {official_value}"
        out.append({"fieldname": claim.fieldname, "claimed_value": claim.value,
                    "claim_literal": claim.literal, "status": status,
                    "claim_citation": {"id": f"news_event:{news.id}", "source_url": news.url,
                                       "excerpt": source_headline, "source": news.source,
                                       "as_of": news.date.isoformat()},
                    "reason": "Exact official field value" if status == "supported"
                              else "Different value in a complete official field",
                    "evidence": {"citation_id": f"document_chunk:{chunk.id}", "document_id": doc.id,
                                 "official_literal": extracted, "locator": locator,
                                 "source_url": record.final_url, "checksum": doc.checksum,
                                 "publication_date": doc.published_at.isoformat() if doc.published_at else None,
                                 "registry_date": (doc.metadata_.get("itu_record") or {}).get("registry_date"),
                                 "fetched_at": record.fetched_at.isoformat(),
                                 "chunk_sha256": chunk.metadata_["chunk_sha256"]}})
    return out
