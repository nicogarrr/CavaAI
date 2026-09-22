"""Institutional ownership endpoints (SEC Form 13F, reviewed managers only)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.manager_holding_ingestion_service import (
    LIMITATIONS,
    REVIEWED_MANAGERS,
    ManagerHoldingIngestionService,
)

router = APIRouter()


@router.get("/managers")
def list_managers() -> dict:
    """Reviewed managers available for 13F sync (exact CIK, never inferred)."""
    return {
        "managers": [{"cik": cik, "name": name} for cik, name in REVIEWED_MANAGERS.items()],
        "limitations": LIMITATIONS,
    }


@router.post("/managers/sync")
def sync_managers(cik: str | None = None, db: Session = Depends(get_db)) -> dict:
    """Sync the latest 13F report for one reviewed manager or all of them."""
    service = ManagerHoldingIngestionService()
    if cik:
        return service.sync_manager(db, cik=cik)
    return service.sync_all(db)


@router.get("/managers/{cik}/changes")
def manager_changes(cik: str, db: Session = Depends(get_db)) -> dict:
    """Quarter-over-quarter 13F position changes for a reviewed manager."""
    return ManagerHoldingIngestionService().changes(db, cik=cik)


@router.get("/managers/{cik}/holdings")
def manager_holdings(cik: str, db: Session = Depends(get_db)) -> dict:
    """Latest 13F report holdings for a reviewed manager, as filed."""
    return ManagerHoldingIngestionService().latest_holdings(db, cik=cik)
