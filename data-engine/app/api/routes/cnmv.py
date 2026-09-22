"""CNMV (regulador oficial ES): otra informacion relevante por emisor. Best-effort."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.services import cnmv_service

router = APIRouter()


@router.get("/oir")
def cnmv_oir(
    ticker: str = Query(min_length=1, max_length=20),
    days: int = Query(default=7, ge=1, le=30),
) -> dict:
    return cnmv_service.get_oir_for_ticker(ticker, days=days)
