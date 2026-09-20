"""Senales insider (Form 4, SEC EDGAR, gratis). Best-effort: nunca 500 por red."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.services import insider_service

router = APIRouter()


@router.get("/signals")
def insider_signals(
    ticker: str = Query(min_length=1, max_length=20),
    cik: str | None = Query(default=None, max_length=10),
    limit: int = Query(default=20, ge=1, le=50),
    notify: bool = Query(default=False),
) -> dict:
    result = insider_service.get_signals_for_ticker(ticker, cik=cik, limit=limit)
    if notify:
        # Enganche minimo Telegram: detras de INSIDER_ALERTS_ENABLED, nunca rompe.
        result["notification"] = insider_service.maybe_notify_insider_buy(
            result.get("ticker", ticker), result.get("signals", [])
        )
    return result
