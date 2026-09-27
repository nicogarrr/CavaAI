"""Descarga privada del vault Obsidian de un ticker."""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Claim, ClaimEvidence, Document, ThesisSection, ThesisVersion
from app.services.company_resolver import resolve_company
from app.services.obsidian_export import Note, Source, build_obsidian_zip

router = APIRouter()


@router.get("/{ticker}/obsidian.zip")
def export_obsidian(ticker: str, db: Session = Depends(get_db)) -> Response:
    company = resolve_company(db, ticker)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    versions = list(
        db.scalars(
            select(ThesisVersion)
            .where(ThesisVersion.company_id == company.id)
            .order_by(ThesisVersion.version, ThesisVersion.id)
        ).all()
    )
    if not versions:
        raise HTTPException(status_code=404, detail="No thesis for ticker")
    version_ids = [v.id for v in versions]
    sections = list(
        db.scalars(
            select(ThesisSection)
            .where(ThesisSection.thesis_version_id.in_(version_ids))
            .order_by(ThesisSection.order_index, ThesisSection.id)
        ).all()
    )
    sections_by_version: dict[int, list[ThesisSection]] = {v.id: [] for v in versions}
    for section in sections:
        sections_by_version[section.thesis_version_id].append(section)
    claims = list(db.scalars(select(Claim).where(Claim.thesis_version_id.in_(version_ids))).all())
    evidence = (
        list(
            db.scalars(select(ClaimEvidence).where(ClaimEvidence.claim_id.in_([c.id for c in claims]))).all()
        )
        if claims
        else []
    )
    doc_ids = [e.document_id for e in evidence if e.document_id is not None]
    documents = (
        {d.id: d for d in db.scalars(select(Document).where(Document.id.in_(doc_ids))).all()}
        if doc_ids
        else {}
    )
    claim_by_id = {c.id: c for c in claims}
    sources: dict[int, list[Source]] = {v.id: [] for v in versions}
    for row in evidence:
        claim = claim_by_id[row.claim_id]
        document = documents.get(row.document_id)
        sources[claim.thesis_version_id].append(
            Source(
                url=row.source_url or (document.source_url if document else "") or "",
                date=document.published_at.date().isoformat() if document and document.published_at else "",
                statement=claim.statement or "",
                tier=row.source_tier or "",
            )
        )
    notes = [
        Note(
            title=f"Tesis {company.ticker} v{v.version}",
            version=v.version,
            date=v.updated_at.date().isoformat() if v.updated_at else "",
            status=v.status or "",
            body=v.thesis_markdown
            or "\n\n".join(
                part
                for part in [
                    v.executive_summary or "",
                    *(
                        f"## {section.title}\n\n{section.body}"
                        for section in sections_by_version[v.id]
                        if section.body
                    ),
                ]
                if part
            ),
            sources=sources[v.id],
        )
        for v in versions
    ]
    content = build_obsidian_zip(company.ticker, notes)
    return Response(
        content=content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="cavaai-obsidian-{company.ticker}.zip"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
