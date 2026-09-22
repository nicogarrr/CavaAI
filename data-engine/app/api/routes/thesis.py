from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Company, ThesisDiff, ThesisSection, ThesisVersion
from app.schemas import ThesisGenerateRequest, ThesisGraphOut, ThesisOut
from app.services.thesis_graph_service import ThesisGraphService
from app.services.thesis_memo import build_memo_markdown
from app.services.thesis_service import ThesisService

router = APIRouter()


@router.post("/generate", response_model=ThesisOut)
def generate_thesis(payload: ThesisGenerateRequest, db: Session = Depends(get_db)) -> ThesisVersion:
    try:
        return ThesisService().generate(db, payload.ticker, payload.force_new_version)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{ticker}/latest", response_model=ThesisOut)
def latest_thesis(ticker: str, db: Session = Depends(get_db)) -> dict:
    service = ThesisService()
    thesis = service.latest(db, ticker)
    if not thesis:
        raise HTTPException(status_code=404, detail="No thesis for ticker")
    # Senal de frescura: hay datos mas nuevos que esta version (hechos,
    # precios, noticias o documentos) -> conviene regenerar la tesis.
    latest_data_at = service.data_freshness(db, thesis.company_id)
    stale = latest_data_at is not None and latest_data_at > thesis.updated_at
    payload = ThesisOut.model_validate(thesis).model_dump()
    payload["stale"] = stale
    payload["latest_data_at"] = latest_data_at
    return payload


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


@router.get("/{ticker}/history")
def thesis_history(ticker: str, db: Session = Depends(get_db)) -> dict:
    """Historial de versiones/aprobaciones: que cambio, cuando y con que resultado.

    Solo lectura de lo persistido (versions + diffs). El "quien" no se
    registra hoy: el historial muestra estado, fecha y resumen del cambio,
    sin inventar actores.
    """
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    versions = list(
        db.scalars(
            select(ThesisVersion)
            .where(ThesisVersion.company_id == company.id)
            .order_by(desc(ThesisVersion.version))
            .limit(50)
        ).all()
    )
    diffs = {
        diff.to_version_id: diff
        for diff in db.scalars(
            select(ThesisDiff).where(ThesisDiff.company_id == company.id)
        ).all()
        if diff.to_version_id is not None
    }
    items = []
    for version in versions:
        diff = diffs.get(version.id)
        items.append(
            {
                "id": version.id,
                "version": version.version,
                "status": version.status,
                "rating": version.rating,
                "red_team_score": version.red_team_score,
                "data_confidence_score": version.data_confidence_score,
                "created_at": version.created_at.isoformat(),
                "updated_at": version.updated_at.isoformat(),
                "diff": (
                    {
                        "change_summary": diff.change_summary,
                        "affected_assumptions": diff.affected_assumptions,
                        "rating_changed": diff.rating_changed,
                        "created_at": diff.created_at.isoformat(),
                    }
                    if diff
                    else None
                ),
            }
        )
    return {"ticker": company.ticker, "count": len(items), "history": items}


@router.get("/{ticker}/memo.md", response_class=PlainTextResponse)
def thesis_memo(ticker: str, db: Session = Depends(get_db)) -> PlainTextResponse:
    """Memo Markdown descargable de la ultima tesis persistida."""
    service = ThesisService()
    thesis = service.latest(db, ticker)
    if not thesis:
        raise HTTPException(status_code=404, detail="No thesis for ticker")
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    latest_data_at = service.data_freshness(db, thesis.company_id)
    stale = latest_data_at is not None and latest_data_at > thesis.updated_at
    markdown = build_memo_markdown(db, company, thesis, stale=stale, latest_data_at=latest_data_at)
    return PlainTextResponse(
        markdown,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="tesis-{company.ticker.lower()}-v{thesis.version}.md"'
        },
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


@router.post("/{ticker}/debate")
async def debate_thesis_endpoint(ticker: str, db: Session = Depends(get_db)) -> dict:
    """Debate bull/bear sobre la última tesis y persiste el veredicto.

    El debate en sí nunca lanza (degrada a veredicto determinista); si el
    upsert de la sección falla, se devuelve el debate con persisted=False.
    """
    from app.services.thesis_debate_service import debate_thesis

    thesis = ThesisService().latest(db, ticker)
    if not thesis:
        raise HTTPException(status_code=404, detail="No thesis for ticker")
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        result = await debate_thesis(
            company.ticker,
            thesis.thesis_markdown or thesis.executive_summary or "",
        )
    except Exception:  # noqa: BLE001 — sin provider LLM: veredicto determinista
        from app.services.thesis_debate_service import _deterministic_verdict

        fallback = _deterministic_verdict(company.ticker, thesis.thesis_markdown or "", "", "")
        result = {
            "ticker": company.ticker,
            "bull_case": "",
            "bear_case": "",
            "verdict": fallback["verdict"],
            "verdict_rationale": fallback["verdict_rationale"],
            "llm_calls": 0,
            "degraded": True,
            "model": "deterministic",
            "materiality_score": 0,
            "portfolio_weight": 0.0,
        }
    persisted = False
    try:
        section = db.scalar(
            select(ThesisSection).where(
                ThesisSection.thesis_version_id == thesis.id,
                ThesisSection.section_key == "thesis_debate",
            )
        )
        if section is None:
            section = ThesisSection(
                thesis_version_id=thesis.id,
                company_id=company.id,
                section_key="thesis_debate",
                title="Thesis debate (bull vs bear)",
                status="published",
                order_index=999,
            )
            db.add(section)
        section.body = f"VEREDICTO: {result['verdict']} | {result['verdict_rationale']}"
        section.metadata_ = {
            "bull_case": result["bull_case"],
            "bear_case": result["bear_case"],
            "verdict": result["verdict"],
            "verdict_rationale": result["verdict_rationale"],
            "llm_calls": result["llm_calls"],
            "degraded": result["degraded"],
            "model": result["model"],
        }
        db.commit()
        persisted = True
    except Exception:  # noqa: BLE001 — el debate ya existe; persistir es best-effort
        db.rollback()
    return {
        "ticker": company.ticker,
        "thesis_version_id": thesis.id,
        "persisted": persisted,
        **result,
    }
