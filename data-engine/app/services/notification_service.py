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
        payload = {
            "alert_id": alert.id,
            "tenant_id": alert.tenant_id,
            "company_id": alert.company_id,
            "severity": alert.severity,
            "type": alert.alert_type,
            "title": alert.title,
            "message": alert.message,
            "created_at": alert.created_at.isoformat(),
        }
        for channel in alert.channels:
            if channel == "in_app":
                deliveries[channel] = self._result("delivered")
                continue
            if channel == "telegram":
                deliveries[channel] = self._dispatch_telegram(settings, payload)
                continue
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
                continue
            try:
                with httpx.Client(timeout=10) as client:
                    response = client.post(
                        endpoint,
                        json={**payload, "channel": channel},
                    )
                    response.raise_for_status()
                deliveries[channel] = self._result("delivered")
            except Exception as exc:
                deliveries[channel] = self._result(
                    "failed", error=f"{type(exc).__name__}: {exc}"
                )
        alert.metadata_ = {
            **(alert.metadata_ or {}),
            "deliveries": deliveries,
        }
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
            # Do not include the response body or URL: both can contain secrets.
            return self._result("failed", error=f"{type(exc).__name__}: {exc}")

    @staticmethod
    def _telegram_text(payload: dict) -> str:
        text = (
            f"[{payload['severity'].upper()}] {payload['title']}\n"
            f"{payload['message']}\n\n"
            f"Ticker/company id: {payload['company_id']}\n"
            f"Alert id: {payload['alert_id']}"
        )
        # Telegram's plain-text sendMessage limit is 4096 characters.
        return text[:4090]

    def _result(self, status: str, error: str | None = None) -> dict:
        return {
            "status": status,
            "attempted_at": datetime.now(UTC).isoformat(),
            "error": error,
        }
