from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Company, ResearchAlert
from app.schemas import (
    ResearchAlertAction,
    ResearchAlertChannels,
    ResearchAlertOut,
)
from app.services.review_alert_service import ReviewAlertService
from app.services.notification_service import NotificationService

router = APIRouter()


@router.get("", response_model=list[ResearchAlertOut])
def list_alerts(
    ticker: str | None = None,
    status: str | None = None,
    include_snoozed: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[ResearchAlert]:
    now = datetime.now(UTC)
    statement = select(ResearchAlert)
    if ticker:
        company = db.scalar(
            select(Company).where(Company.ticker == ticker.upper())
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
        statement = statement.where(ResearchAlert.company_id == company.id)
    if status:
        statement = statement.where(ResearchAlert.status == status)
    elif not include_snoozed:
        statement = statement.where(
            or_(
                ResearchAlert.status != "snoozed",
                ResearchAlert.snoozed_until <= now,
            )
        )
    alerts = list(
        db.scalars(
            statement.order_by(
                desc(ResearchAlert.created_at)
            ).limit(limit)
        ).all()
    )
    for alert in alerts:
        if (
            alert.status == "snoozed"
            and alert.snoozed_until
            and alert.snoozed_until <= now
        ):
            alert.status = "open"
            alert.snoozed_until = None
    db.commit()
    return alerts


@router.post("/{alert_id}/action", response_model=ResearchAlertOut)
def action_alert(
    alert_id: int,
    payload: ResearchAlertAction,
    db: Session = Depends(get_db),
) -> ResearchAlert:
    alert = db.get(ResearchAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    try:
        ReviewAlertService().transition_alert(
            alert,
            action=payload.action,
            actor=payload.actor,
            snoozed_until=payload.snoozed_until,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(alert)
    return alert


@router.post("/{alert_id}/dispatch")
def dispatch_alert(
    alert_id: int, db: Session = Depends(get_db)
) -> dict:
    alert = db.get(ResearchAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {
        "alert_id": alert.id,
        "deliveries": NotificationService().dispatch(db, alert),
    }


@router.patch("/{alert_id}/channels", response_model=ResearchAlertOut)
def update_alert_channels(
    alert_id: int,
    payload: ResearchAlertChannels,
    db: Session = Depends(get_db),
) -> ResearchAlert:
    alert = db.get(ResearchAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.channels = list(dict.fromkeys(payload.channels))
    db.commit()
    db.refresh(alert)
    return alert
