from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import CustomMetricDefinition, SavedScreen
from app.services.screener_service import CustomMetricService, ScreenerService


router = APIRouter()


class CustomMetricCreate(BaseModel):
    metric_key: str = Field(min_length=2, max_length=160)
    name: str = Field(min_length=1, max_length=240)
    formula: str = Field(min_length=1, max_length=1000)
    unit: str = Field(default="decimal", min_length=1, max_length=40)
    description: str = Field(default="", max_length=5000)


class Criterion(BaseModel):
    left: str = Field(min_length=1, max_length=1000)
    operator: Literal[">", ">=", "<", "<=", "==", "!="]
    right: str = Field(min_length=1, max_length=1000)


class ScreenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=5000)
    criteria: list[Criterion] = Field(min_length=1, max_length=30)
    ranking_formula: str | None = Field(default=None, max_length=1000)
    ranking_direction: Literal["asc", "desc"] = "desc"
    alerts_enabled: bool = True


class AdHocScreen(BaseModel):
    criteria: list[Criterion] = Field(min_length=1, max_length=30)
    ranking_formula: str | None = Field(default=None, max_length=1000)
    ranking_direction: Literal["asc", "desc"] = "desc"


def _metric_payload(row: CustomMetricDefinition) -> dict[str, Any]:
    return {
        "id": row.id,
        "metric_key": row.metric_key,
        "name": row.name,
        "formula": row.formula,
        "unit": row.unit,
        "description": row.description,
        "version": row.version,
        "active": row.active,
        "metadata": row.metadata_,
        "created_at": row.created_at,
    }


def _screen_payload(row: SavedScreen) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "criteria": row.criteria,
        "ranking_formula": row.ranking_formula,
        "ranking_direction": row.ranking_direction,
        "alerts_enabled": row.alerts_enabled,
        "active": row.active,
        "last_run_at": row.last_run_at,
        "created_at": row.created_at,
    }


@router.get("/custom-metrics")
def list_custom_metrics(db: Session = Depends(get_db)) -> list[dict]:
    return [_metric_payload(row) for row in CustomMetricService.active(db)]


@router.post("/custom-metrics", status_code=201)
def create_custom_metric(
    payload: CustomMetricCreate, db: Session = Depends(get_db)
) -> dict:
    try:
        row = CustomMetricService().create(db, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _metric_payload(row)


@router.get("/screens")
def list_screens(db: Session = Depends(get_db)) -> list[dict]:
    return [
        _screen_payload(row)
        for row in db.scalars(select(SavedScreen).order_by(SavedScreen.name)).all()
    ]


@router.post("/screens", status_code=201)
def create_screen(payload: ScreenCreate, db: Session = Depends(get_db)) -> dict:
    try:
        row = ScreenerService().create_screen(
            db,
            name=payload.name,
            description=payload.description,
            criteria=[item.model_dump() for item in payload.criteria],
            ranking_formula=payload.ranking_formula,
            ranking_direction=payload.ranking_direction,
            alerts_enabled=payload.alerts_enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _screen_payload(row)


@router.post("/screens/{screen_id}/run")
def run_saved_screen(screen_id: int, db: Session = Depends(get_db)) -> dict:
    screen = db.get(SavedScreen, screen_id)
    if screen is None:
        raise HTTPException(status_code=404, detail="Saved screen not found")
    return ScreenerService().run_saved(db, screen)


@router.post("/run")
def run_ad_hoc_screen(payload: AdHocScreen, db: Session = Depends(get_db)) -> dict:
    try:
        return ScreenerService().run(
            db,
            criteria=[item.model_dump() for item in payload.criteria],
            ranking_formula=payload.ranking_formula,
            ranking_direction=payload.ranking_direction,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
