"""Authenticated, tenant-scoped AST satellite snapshot."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.asts_catalog_service import read_catalog
from app.services.asts_llm_service import analyze_asts_catalog

router = APIRouter()


@router.get("/satellites")
def ast_satellites(db: Session = Depends(get_db)) -> dict:
    return read_catalog(db)


@router.get("/llm-analysis")
def ast_llm_analysis(db: Session = Depends(get_db)) -> dict:
    return analyze_asts_catalog(db)
