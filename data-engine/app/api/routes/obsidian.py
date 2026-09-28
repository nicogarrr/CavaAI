"""Descarga privada del vault Obsidian: por ticker o del tenant completo."""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import (
    Claim,
    ClaimEvidence,
    Company,
    Document,
    Position,
    ThesisSection,
    ThesisVersion,
    WatchItem,
)
from app.services.company_resolver import resolve_company
from app.services.obsidian_export import (
    CompanyEntry,
    Note,
    Source,
    build_obsidian_vault,
    build_obsidian_zip,
    find_mentions,
)

router = APIRouter()
vault_router = APIRouter()


def _zip_response(content: bytes, filename: str) -> Response:
    return Response(
        content=content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _load_thesis_notes(db: Session, company: Company) -> list[Note]:
    """Tesis persistidas del tenant para una empresa, con sus fuentes reales.

    ThesisVersion/Claim/ClaimEvidence/Document son TenantOwned: la sesión ya
    filtra por el tenant firmado, así que ninguna nota mezcla tenants.
    """
    versions = list(
        db.scalars(
            select(ThesisVersion)
            .where(ThesisVersion.company_id == company.id)
            .order_by(ThesisVersion.version, ThesisVersion.id)
        ).all()
    )
    if not versions:
        return []
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
    return [
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


@router.get("/{ticker}/obsidian.zip")
def export_obsidian(ticker: str, db: Session = Depends(get_db)) -> Response:
    company = resolve_company(db, ticker)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    notes = _load_thesis_notes(db, company)
    if not notes:
        raise HTTPException(status_code=404, detail="No thesis for ticker")
    content = build_obsidian_zip(company.ticker, notes)
    return _zip_response(content, f"cavaai-obsidian-{company.ticker}.zip")


@vault_router.get("/vault.zip")
def export_obsidian_vault(db: Session = Depends(get_db)) -> Response:
    """Vault Markdown del tenant: cartera + watchlist, solo datos persistidos.

    Coste cero: ni LLM ni red, solo lecturas de la base ya filtradas por el
    tenant firmado (Position/WatchItem/tesis son TenantOwned). Los símbolos
    de watchlist sin empresa en el universo se listan como "sin datos de
    empresa" en vez de inventarse una ficha.
    """
    # Solo tenencias vivas: una posición cerrada (quantity=0 tras vender) es
    # historial del ledger, no cartera; el resto de la app la trata igual.
    positions = list(db.scalars(select(Position)).all())
    company_ids = sorted(
        {position.company_id for position in positions if position.quantity > 0}
    )
    companies: dict[str, Company] = {}
    if company_ids:
        companies = {
            company.ticker: company
            for company in db.scalars(select(Company).where(Company.id.in_(company_ids))).all()
        }
    portfolio_tickers = set(companies)
    watch_tickers: set[str] = set()
    unresolved: list[str] = []
    for item in db.scalars(select(WatchItem)).all():
        company = resolve_company(db, item.symbol)
        if company is None:
            unresolved.append(item.symbol)
            continue
        watch_tickers.add(company.ticker)
        companies.setdefault(company.ticker, company)

    entries = [
        CompanyEntry(
            ticker=ticker,
            name=company.name or "",
            sector=company.sector or "",
            industry=company.industry or "",
            in_portfolio=ticker in portfolio_tickers,
            in_watchlist=ticker in watch_tickers,
        )
        for ticker, company in companies.items()
    ]
    notes_by_ticker: dict[str, list[Note]] = {}
    texts: dict[str, str] = {}
    for ticker, company in companies.items():
        notes = _load_thesis_notes(db, company)
        if not notes:
            continue
        notes_by_ticker[ticker] = notes
        texts[ticker] = "\n\n".join(
            part
            for note in notes
            for part in [note.body, *(source.statement for source in note.sources)]
            if part
        )
    names = {ticker: company.name or "" for ticker, company in companies.items()}
    mentions = {
        ticker: found
        for ticker, text in texts.items()
        if (found := find_mentions(text, {other: name for other, name in names.items() if other != ticker}))
    }
    content = build_obsidian_vault(entries, notes_by_ticker, mentions, unresolved_symbols=unresolved)
    return _zip_response(content, "cavaai-obsidian-vault.zip")
