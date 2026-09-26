from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AlertDelivery, ResearchAlert

# Un claim 'sending' mas viejo que esto se considera abandonado (worker muerto
# entre el envio y el commit del resultado) y vuelve a ser reclamable. Es el
# unico residuo at-least-once: si el envio original si llego, la recuperacion
# puede repetir ESE canal una vez pasado el TTL.
STALE_CLAIM_SECONDS = 600


class NotificationService:
    """Dispatch alert channels without coupling research logic to one vendor."""

    def dispatch(self, db: Session, alert: ResearchAlert) -> dict:
        settings = get_settings()
        deliveries: dict[str, dict] = {}
        # Score Jev adjuntado por el emisor (alert_rule_service, best-effort):
        # sin TYPESAFE_API_KEY no hay `jev_urgency` y el texto sale sin línea Jev.
        jev_urgency = (alert.metadata_ or {}).get("jev_urgency") or {}
        payload = {
            "alert_id": alert.id,
            "tenant_id": alert.tenant_id,
            "company_id": alert.company_id,
            "severity": alert.severity,
            "type": alert.alert_type,
            "title": alert.title,
            "message": alert.message,
            "created_at": alert.created_at.isoformat(),
            "jev_urgency": jev_urgency,
        }
        for channel in alert.channels:
            self._ensure_delivery_row(db, alert, channel)
            if not self._claim_delivery(db, alert, channel):
                # Otro worker la tiene ('sending') o ya esta entregada: nunca
                # reenviar lo que no se ha reclamado.
                row = self._get_delivery(db, alert, channel)
                deliveries[channel] = self._result(
                    row.status if row is not None else "pending",
                    error=row.last_error if row is not None else None,
                )
                continue
            try:
                if channel == "in_app":
                    result = self._result("delivered")
                elif channel == "telegram":
                    result = self._dispatch_telegram(settings, payload)
                else:
                    result = self._dispatch_webhook(settings, payload, channel)
            except Exception:
                # El commit del resultado tambien puede fallar: la fila queda
                # en 'sending' y un retry inmediato NO la reclama (sin
                # reenvio). Solo un claim expirado (> STALE_CLAIM_SECONDS)
                # vuelve a ser elegible.
                self._finish_delivery(db, alert, channel, "failed", "dispatch_error")
                deliveries[channel] = self._result("failed", error="dispatch_error")
                continue
            self._finish_delivery(db, alert, channel, result["status"], result["error"])
            deliveries[channel] = result
        # Espejo NO autoritativo en metadata_ para lectores antiguos; el
        # estado real vive en alert_deliveries.
        alert.metadata_ = {**(alert.metadata_ or {}), "deliveries": deliveries}
        db.commit()
        db.refresh(alert)
        return deliveries

    def _dispatch_webhook(self, settings, payload: dict, channel: str) -> dict:
        endpoint = (
            getattr(settings, "alert_email_webhook_url", None)
            if channel == "email"
            else getattr(settings, "alert_push_webhook_url", None)
            if channel == "push"
            else None
        )
        if not endpoint:
            return self._result(
                "not_configured",
                error=f"No webhook configured for {channel}",
            )
        try:
            with httpx.Client(timeout=10) as client:
                response = client.post(
                    endpoint,
                    json={**payload, "channel": channel},
                )
                response.raise_for_status()
            return self._result("delivered")
        except Exception as exc:
            # Webhook errors can contain signed URLs, request bodies and
            # provider paths. Persist only the exception class.
            return self._result("failed", error=type(exc).__name__)

    def _ensure_delivery_row(self, db: Session, alert: ResearchAlert, channel: str) -> None:
        if self._get_delivery(db, alert, channel) is not None:
            return
        db.add(
            AlertDelivery(
                tenant_id=alert.tenant_id, alert_id=alert.id, channel=channel
            )
        )
        try:
            db.commit()
        except IntegrityError:
            # Otro worker creo la fila primero (UNIQUE alert_id+channel).
            db.rollback()

    def _get_delivery(
        self, db: Session, alert: ResearchAlert, channel: str
    ) -> AlertDelivery | None:
        return db.execute(
            select(AlertDelivery).where(
                AlertDelivery.alert_id == alert.id,
                AlertDelivery.channel == channel,
            )
        ).scalar_one_or_none()

    def _claim_delivery(self, db: Session, alert: ResearchAlert, channel: str) -> bool:
        """Claim atomico: un solo UPDATE con la condicion de elegibilidad.

        Dos workers concurrentes: solo uno obtiene fila (RETURNING). Un
        commit fallido tras el envio deja 'sending' reciente -> no elegible
        -> el retry no reenvia. 'sending' expirado (worker muerto) vuelve a
        ser elegible pasado STALE_CLAIM_SECONDS.
        """
        stale_before = datetime.now(UTC) - timedelta(seconds=STALE_CLAIM_SECONDS)
        result = db.execute(
            update(AlertDelivery)
            .where(
                AlertDelivery.alert_id == alert.id,
                AlertDelivery.channel == channel,
                or_(
                    AlertDelivery.status.in_(("pending", "failed")),
                    and_(
                        AlertDelivery.status == "sending",
                        AlertDelivery.updated_at < stale_before,
                    ),
                )
            )
            .values(status="sending", attempts=AlertDelivery.attempts + 1, last_error=None)
            .returning(AlertDelivery.id)
        )
        claimed = result.scalar_one_or_none() is not None
        # El claim queda persistido ANTES de enviar.
        db.commit()
        return claimed

    def _finish_delivery(
        self,
        db: Session,
        alert: ResearchAlert,
        channel: str,
        status: str,
        error: str | None,
    ) -> None:
        db.execute(
            update(AlertDelivery)
            .where(
                AlertDelivery.alert_id == alert.id,
                AlertDelivery.channel == channel,
            )
            .values(status=status, last_error=error)
        )
        db.commit()

    def _dispatch_telegram(self, settings, payload: dict) -> dict:
        token = settings.telegram_bot_token
        chat_id = settings.telegram_chat_id
        if not settings.telegram_enabled or not token or not chat_id:
            return self._result(
                "not_configured",
                error="Telegram notifications require TELEGRAM_ENABLED, TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID",
            )
        text = self._telegram_text(payload)
        endpoint = (
            f"{settings.telegram_api_base_url.rstrip('/')}/bot{token}/sendMessage"
        )
        try:
            with httpx.Client(timeout=settings.telegram_timeout_seconds) as client:
                response = client.post(
                    endpoint,
                    json={"chat_id": chat_id, "text": text},
                )
                response.raise_for_status()
            return self._result("delivered")
        except Exception as exc:
            # Never persist upstream exception text: it may contain the bot token,
            # the fully-qualified endpoint, the request body, or a response body.
            return self._result("failed", error=type(exc).__name__)

    @staticmethod
    def _telegram_text(payload: dict) -> str:
        text = (
            f"[{payload['severity'].upper()}] {payload['title']}\n"
            f"{payload['message']}\n\n"
            f"Ticker/company id: {payload['company_id']}\n"
            f"Alert id: {payload['alert_id']}"
        )
        # Urgencia Jev (1 llamada en el emisor, ~$0.042/MTok in): solo aparece
        # si el emisor adjuntó `jev_urgency`; sin key no hay línea (fallback).
        jev = payload.get("jev_urgency") or {}
        if jev.get("label"):
            try:
                conf = float(jev.get("confidence") or 0.0)
            except (TypeError, ValueError):
                conf = 0.0
            text += f"\nJev urgency: {jev['label']} (conf {conf:.2f})"
        # Telegram's plain-text sendMessage limit is 4096 characters.
        return text[:4090]

    def _result(self, status: str, error: str | None = None) -> dict:
        return {
            "status": status,
            "attempted_at": datetime.now(UTC).isoformat(),
            "error": error,
        }
