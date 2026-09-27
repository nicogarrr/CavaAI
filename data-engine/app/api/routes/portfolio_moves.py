"""Read-only tenant-scoped portfolio movement digest."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.portfolio_moves_service import latest_digest

router = APIRouter()


@router.get("/moves")
def moves(db: Session = Depends(get_db)) -> dict:
    return latest_digest(db)
