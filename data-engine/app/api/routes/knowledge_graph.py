from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Company
from app.services.knowledge_graph_service import KnowledgeGraphService


router = APIRouter()


@router.post("/sync")
def sync_knowledge_graph(db: Session = Depends(get_db)) -> dict:
    try:
        return KnowledgeGraphService().sync(db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
def knowledge_graph(
    node_types: str | None = None,
    ticker: str | None = None,
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> dict:
    company_id = None
    if ticker:
        company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
        if company is None:
            raise HTTPException(status_code=404, detail="Company not found")
        company_id = company.id
    types = (
        {item.strip() for item in node_types.split(",") if item.strip()}
        if node_types
        else None
    )
    return KnowledgeGraphService().graph(
        db, node_types=types, company_id=company_id, limit=limit
    )


@router.get("/nodes/{node_id}/neighbors")
def knowledge_graph_neighbors(
    node_id: int,
    depth: int = Query(default=2, ge=1, le=4),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return KnowledgeGraphService().neighborhood(db, node_id, depth=depth)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
