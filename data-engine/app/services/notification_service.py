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

    def _result(self, status: str, error: str | None = None) -> dict:
        return {
            "status": status,
            "attempted_at": datetime.now(UTC).isoformat(),
            "error": error,
        }
