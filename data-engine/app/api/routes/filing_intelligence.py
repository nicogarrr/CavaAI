"""Persisted filing analyses. Reads never trigger a download or analysis."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Document
from app.services.company_resolver import resolve_company
from app.services.filing_intelligence import KEY

router = APIRouter()


@router.get("/{ticker}/filing-intelligence")
def filing_intelligence(
    ticker: str, page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db),
) -> dict:
    company = resolve_company(db, ticker)
    if company is None:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    tenant = db.info.get("tenant_id")
    if tenant is None:
        raise HTTPException(status_code=401, detail="Se requiere una identidad de Research")
    filters = (Document.tenant_id == tenant, Document.company_id == company.id,
               Document.metadata_[KEY]["version"].as_string().is_not(None))
    total = db.scalar(select(func.count(Document.id)).where(*filters)) or 0
    rows = db.scalars(select(Document).where(*filters).order_by(
        desc(Document.published_at).nullslast(), desc(Document.id),
    ).offset((page - 1) * page_size).limit(page_size)).all()
    return {"status": "ready" if total else "insufficient_data", "page": page,
            "page_size": page_size, "total": total, "items": [row.metadata_[KEY] for row in rows]}
