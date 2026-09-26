from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import get_settings
from app.models import AlertRule, Company, ResearchAlert
from app.schemas import (
    AlertRuleOut,
    ResearchAlertAction,
    ResearchAlertChannels,
    ResearchAlertOut,
)
from app.services.review_alert_service import ReviewAlertService
from app.services.alert_rule_service import AlertRuleService
from app.services.notification_service import NotificationService
from app.services.company_resolver import resolve_company

router = APIRouter()


class ManualAlertCreate(BaseModel):
    ticker: str = Field(min_length=1, max_length=20)
    alert_type: Literal["price_above", "price_below", "price_change", "news", "earnings"]
    operator: Literal[">", "<", ">=", "<=", "=="]
    value: float | str


@router.post("", response_model=AlertRuleOut, status_code=201)
def create_alert(
    payload: ManualAlertCreate, db: Session = Depends(get_db)
) -> AlertRule:
    company = db.scalar(
        select(Company).where(Company.ticker == payload.ticker.upper())
    )
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return AlertRuleService().create(
        db,
        company,
        rule_type=payload.alert_type,
        operator=payload.operator,
        value=payload.value,
    )


@router.get("/rules", response_model=list[AlertRuleOut])
def list_alert_rules(
    ticker: str | None = None,
    active: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
) -> list[AlertRule]:
    statement = select(AlertRule)
    if ticker:
        company = resolve_company(db, ticker)
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
        statement = statement.where(AlertRule.company_id == company.id)
    if active is not None:
        statement = statement.where(AlertRule.active.is_(active))
    return list(
        db.scalars(statement.order_by(desc(AlertRule.created_at)).limit(limit).offset(offset)).all()
    )


@router.get("/telegram-status")
def telegram_status() -> dict:
    """Presencia de la configuracion Telegram para la guia de /alerts.

    Solo booleanos: ningun secreto (token, chat_id, URL) sale por la API.
    """
    settings = get_settings()
    enabled = bool(settings.telegram_enabled)
    has_token = bool(settings.telegram_bot_token)
    has_chat = bool(settings.telegram_chat_id)
    return {
        "enabled": enabled,
        "has_bot_token": has_token,
        "has_chat_id": has_chat,
        "configured": enabled and has_token and has_chat,
    }


@router.post("/rules/evaluate")
def evaluate_alert_rules(db: Session = Depends(get_db)) -> dict:
    results = AlertRuleService().evaluate_all(db)
    return {"status": "ok", "evaluated": len(results), "results": results}


@router.delete("/rules/{rule_id}", response_model=AlertRuleOut)
def deactivate_alert_rule(
    rule_id: int, db: Session = Depends(get_db)
) -> AlertRule:
    rule = db.get(AlertRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    rule.active = False
    db.commit()
    db.refresh(rule)
    return rule


def _snooze_expired(snoozed_until: datetime | None, now: datetime) -> bool:
    """¿Caducó el snooze?

    `snoozed_until` llega del cliente como `datetime` (Pydantic no le impone
    zona) y la base lo devuelve naive: SQLite no guarda el offset, asi que al
    releerlo se pierde el tz y `naive <= aware` lanza
    `TypeError: can't compare offset-naive and offset-aware datetimes`. Se
    normaliza a UTC asumiendo que un valor naive ya esta en UTC, que es como se
    escribe en el resto de la app.
    """
    if snoozed_until is None:
        return False
    value = (
        snoozed_until
        if snoozed_until.tzinfo is not None
        else snoozed_until.replace(tzinfo=UTC)
    )
    return value <= now


@router.get("", response_model=list[ResearchAlertOut])
def list_alerts(
    ticker: str | None = None,
    status: str | None = None,
    include_snoozed: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[ResearchAlertOut]:
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
        # Solo REAPARECEN las alertas cuyo snooze ya caduco: un snooze sin
        # fecha es indefinido (silenciar = ocultar) y uno con fecha futura
        # sigue activo; ambos quedan fuera salvo include_snoozed=True.
        # (`snoozed_until <= now` con NULL evalua a NULL -> excluida, que es
        # exactamente la semantica de snooze indefinido.)
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
    # Un GET no escribe. Antes el handler reabria las alertas cuyo snooze habia
    # caducado y hacia commit, lo que hacia la operacion no idempotente (dos
    # GET seguidos no dan el mismo resultado), rompia cualquier cache HTTP de la
    # ruta, y podia devolver 500 en un camino de lectura. Aqui solo se refleja
    # el estado derivado en la respuesta, sin tocar la fila: la fila queda
    # 'snoozed' en base y cada respuesta deriva a 'open' sin escritura.
    # El estado derivado se refleja en DTOs, NUNCA en las entidades ORM:
    # mutarlas dejaba la sesion sucia y cualquier commit posterior del mismo
    # request podia flushear una escritura desde un GET.
    result: list[ResearchAlertOut] = []
    for alert in alerts:
        out = ResearchAlertOut.model_validate(alert)
        if alert.status == "snoozed" and _snooze_expired(alert.snoozed_until, now):
            out.status = "open"
            out.snoozed_until = None
        result.append(out)
    return result


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
