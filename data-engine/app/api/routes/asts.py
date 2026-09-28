"""Authenticated, tenant-scoped AST satellite snapshot."""

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.asts_catalog_service import read_catalog, read_orbit_history, read_orbit_overview
from app.services.asts_llm_service import analyze_asts_catalog

router = APIRouter()


@router.get("/satellites")
def ast_satellites(db: Session = Depends(get_db)) -> dict:
    return read_catalog(db)


@router.get("/llm-analysis")
def ast_llm_analysis(db: Session = Depends(get_db)) -> dict:
    return analyze_asts_catalog(db)


@router.get("/satellites/{norad_cat_id}/orbit")
def ast_satellite_orbit(norad_cat_id: int = Path(ge=1), db: Session = Depends(get_db)) -> dict:
    return read_orbit_history(db, norad_cat_id)


@router.get("/orbits")
def ast_orbits(db: Session = Depends(get_db)) -> dict:
    return read_orbit_overview(db)
