"""Read-only, authenticated market context from persisted snapshots."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.market_snapshot_service import latest_snapshot

router = APIRouter()


@router.get("/regime")
def regime(db: Session = Depends(get_db)) -> dict:
    return latest_snapshot(db)
