"""Authenticated, tenant-scoped AST satellite snapshot."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.asts_catalog_service import read_catalog

router = APIRouter()


@router.get("/satellites")
def ast_satellites(db: Session = Depends(get_db)) -> dict:
    return read_catalog(db)
