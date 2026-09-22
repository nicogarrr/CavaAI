"""Corporate actions: splits, reverse splits, ticker changes."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
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


def _payload(action, ticker: str | None) -> dict:
    return {
        "id": action.id,
        "ticker": ticker,
        "action_type": action.action_type,
        "effective_date": action.effective_date.isoformat(),
        "ratio": float(action.ratio),
        "description": action.description,
        "applied": action.applied,
        "applied_at": action.applied_at.isoformat() if action.applied_at else None,
    }


@router.get("")
def list_actions(
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    db: Session = Depends(get_db),
) -> list[dict]:
    service = CorporateActionService()
    actions = service.list_actions(db, limit=limit)
    # Lote: tickers en 1 query (anti N+1 de db.get por acción).
    company_ids = {action.company_id for action in actions if action.company_id}
    tickers = (
        dict(
            db.execute(
                select(Company.id, Company.ticker).where(Company.id.in_(company_ids))
            ).all()
        )
        if company_ids
        else {}
    )
    return [_payload(action, tickers.get(action.company_id)) for action in actions]


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
    company = db.get(Company, action.company_id)
    return _payload(action, company.ticker if company else None)


@router.post("/{action_id}/apply")
def apply_action(action_id: int, db: Session = Depends(get_db)) -> dict:
    service = CorporateActionService()
    try:
        action = service.apply_action(db, action_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    company = db.get(Company, action.company_id)
    return _payload(action, company.ticker if company else None)


@router.delete("/{action_id}", status_code=204)
def delete_action(action_id: int, db: Session = Depends(get_db)) -> None:
    service = CorporateActionService()
    try:
        if not service.delete_action(db, action_id):
            raise HTTPException(status_code=404, detail="Corporate action not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc