from datetime import UTC, datetime

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import ResearchAlert


class NotificationService:
    """Dispatch alert channels without coupling research logic to one vendor."""

    def dispatch(self, db: Session, alert: ResearchAlert) -> dict:
        settings = get_settings()
        deliveries = dict((alert.metadata_ or {}).get("deliveries", {}))
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
            # Dedup por canal: un retry nunca reenvia un canal ya entregado.
            if deliveries.get(channel, {}).get("status") == "delivered":
                continue
            # Outbox: el intento queda persistido ANTES de enviar, y el
            # resultado DESPUES de cada canal. Si el proceso muere a mitad,
            # el retry ve lo ya entregado y no lo repite (at-least-once: un
            # commit fallido justo tras un envio puede repetir ESE canal;
            # sin idempotency keys del proveedor no se puede acotar mas).
            deliveries[channel] = self._result("pending")
            alert.metadata_ = {**(alert.metadata_ or {}), "deliveries": deliveries}
            db.commit()
            if channel == "in_app":
                deliveries[channel] = self._result("delivered")
            elif channel == "telegram":
                deliveries[channel] = self._dispatch_telegram(settings, payload)
            else:
                endpoint = (
                    getattr(settings, "alert_email_webhook_url", None)
                    if channel == "email"
                    else getattr(settings, "alert_push_webhook_url", None)
                    if channel == "push"
                    else None
                )
                if not endpoint:
                    deliveries[channel] = self._result(
                        "not_configured",
                        error=f"No webhook configured for {channel}",
                    )
                else:
                    try:
                        with httpx.Client(timeout=10) as client:
                            response = client.post(
                                endpoint,
                                json={**payload, "channel": channel},
                            )
                            response.raise_for_status()
                        deliveries[channel] = self._result("delivered")
                    except Exception as exc:
                        # Webhook errors can contain signed URLs, request bodies and
                        # provider paths. Persist only the exception class.
                        deliveries[channel] = self._result(
                            "failed", error=type(exc).__name__
                        )
            alert.metadata_ = {**(alert.metadata_ or {}), "deliveries": deliveries}
            db.commit()
        db.refresh(alert)
        return deliveries

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
