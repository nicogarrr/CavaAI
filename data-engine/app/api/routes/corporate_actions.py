"""Corporate actions: splits, reverse splits, ticker changes."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Company
from app.services.corporate_actions_service import CorporateActionService

router = APIRouter()


class CorporateActionInput(BaseModel):
    ticker: str = Field(min_length=1, max_length=20)
    action_type: str = Field(pattern="^(split|reverse_split|ticker_change|merger|spin_off)$")
    effective_date: date
    ratio: float = Field(gt=0, le=1_000_000)
    description: str = Field(default="", max_length=500)
    apply_now: bool = Field(default=True)


def _payload(action, db: Session) -> dict:
    company = db.get(Company, action.company_id)
    return {
        "id": action.id,
        "ticker": company.ticker if company else None,
        "action_type": action.action_type,
        "effective_date": action.effective_date.isoformat(),
        "ratio": float(action.ratio),
        "description": action.description,
        "applied": action.applied,
        "applied_at": action.applied_at.isoformat() if action.applied_at else None,
    }


@router.get("")
def list_actions(db: Session = Depends(get_db)) -> list[dict]:
    service = CorporateActionService()
    return [_payload(action, db) for action in service.list_actions(db)]


@router.post("", status_code=201)
def create_action(payload: CorporateActionInput, db: Session = Depends(get_db)) -> dict:
    service = CorporateActionService()
    try:
        action = service.create_action(
            db,
            ticker=payload.ticker,
            action_type=payload.action_type,
            effective_date=payload.effective_date,
            ratio=Decimal(str(payload.ratio)),
            description=payload.description,
            apply_now=payload.apply_now,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _payload(action, db)


@router.post("/{action_id}/apply")
def apply_action(action_id: int, db: Session = Depends(get_db)) -> dict:
    service = CorporateActionService()
    try:
        action = service.apply_action(db, action_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _payload(action, db)


@router.delete("/{action_id}", status_code=204)
def delete_action(action_id: int, db: Session = Depends(get_db)) -> None:
    service = CorporateActionService()
    try:
        if not service.delete_action(db, action_id):
            raise HTTPException(status_code=404, detail="Corporate action not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc