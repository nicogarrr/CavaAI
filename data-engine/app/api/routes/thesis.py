from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Claim, Company, ThesisSection, ThesisVersion
from app.schemas import ThesisGenerateRequest, ThesisGraphOut, ThesisOut
from app.services.thesis_graph_service import ThesisGraphService
from app.services.thesis_service import ThesisService

router = APIRouter()


@router.get("/{ticker}/epub")
def download_thesis_epub(ticker: str, db: Session = Depends(get_db)) -> Response:
    """Descarga la última tesis del ticker en formato EPUB.

    Degrada a 404 limpio si no hay tesis (ni empresa) para el ticker.
    """
    import re
    from datetime import date as _date

    from app.services.thesis_epub_service import (
        EpubSection,
        ThesisEpubData,
        build_thesis_epub,
    )

    clean = re.sub(r"[^A-Z0-9.\-]", "", (ticker or "").upper())
    if not clean:
        raise HTTPException(status_code=404, detail="No thesis for ticker")

    thesis = ThesisService().latest(db, clean)
    if thesis is None:
        raise HTTPException(status_code=404, detail="No thesis for ticker")
    company = db.scalar(select(Company).where(Company.ticker == clean))
    if company is None:
        raise HTTPException(status_code=404, detail="No thesis for ticker")

    sections = list(
        db.scalars(
            select(ThesisSection)
            .where(ThesisSection.thesis_version_id == thesis.id)
            .order_by(ThesisSection.order_index, ThesisSection.id)
        ).all()
    )
    claims = list(
        db.scalars(
            select(Claim)
            .where(Claim.company_id == company.id)
            .order_by(desc(Claim.materiality_score), Claim.id)
            .limit(50)
        ).all()
    )

    citations: list[str] = []
    for claim in claims:
        urls = [
            ev.source_url
            for ev in (claim.evidence or [])
            if getattr(ev, "source_url", None)
        ][:3]
        suffix = f" ({', '.join(urls)})" if urls else ""
        citations.append(f"[{claim.status}] {claim.statement}{suffix}")

    created = getattr(thesis, "created_at", None)
    generated_on = created.date().isoformat() if created else _date.today().isoformat()

    payload = build_thesis_epub(
        ThesisEpubData(
            ticker=clean,
            company_name=company.name or "",
            version=thesis.version,
            rating=thesis.rating or "watch",
            status=thesis.status or "draft",
            generated_on=generated_on,
            executive_summary=thesis.executive_summary or "",
            sections=[
                EpubSection(title=section.title or section.section_key, body=section.body or "")
                for section in sections
            ],
            citations=citations,
        )
    )
    return Response(
        content=payload,
        media_type="application/epub+zip",
        headers={
            "Content-Disposition": f'attachment; filename="cavaai-thesis-{clean}-v{thesis.version}.epub"'
        },
    )



@router.post("/generate", response_model=ThesisOut)
def generate_thesis(payload: ThesisGenerateRequest, db: Session = Depends(get_db)) -> ThesisVersion:
    try:
        return ThesisService().generate(db, payload.ticker, payload.force_new_version)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{ticker}/latest", response_model=ThesisOut)
def latest_thesis(ticker: str, db: Session = Depends(get_db)) -> ThesisVersion:
    thesis = ThesisService().latest(db, ticker)
    if not thesis:
        raise HTTPException(status_code=404, detail="No thesis for ticker")
    return thesis


@router.get("/{ticker}/versions", response_model=list[ThesisOut])
def thesis_versions(
    ticker: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[ThesisVersion]:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return list(
        db.scalars(
            select(ThesisVersion)
            .where(ThesisVersion.company_id == company.id)
            .order_by(desc(ThesisVersion.version))
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )


@router.get("/{ticker}/graph", response_model=ThesisGraphOut)
def thesis_graph(ticker: str, db: Session = Depends(get_db)) -> dict:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        thesis, nodes, edges = ThesisGraphService().read(db, company)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "ticker": company.ticker,
        "thesis_version_id": thesis.id,
        "nodes": nodes,
        "edges": edges,
    }


@router.post("/{ticker}/graph/refresh", response_model=ThesisGraphOut)
def refresh_thesis_graph(ticker: str, db: Session = Depends(get_db)) -> dict:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        thesis, nodes, edges = ThesisGraphService().build(db, company)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "ticker": company.ticker,
        "thesis_version_id": thesis.id,
        "nodes": nodes,
        "edges": edges,
    }
