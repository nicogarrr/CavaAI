"""Signed identity bridge between the Next.js server and Research OS.

The browser never creates these headers. Next.js server actions sign the active
Better Auth identity with a shared secret, and FastAPI verifies it before a
tenant-scoped database session is opened.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import time

from fastapi import Header, HTTPException, status

from app.core.config import get_settings


@dataclass(frozen=True)
class ResearchPrincipal:
    user_id: str
    tenant_external_id: str


def signature_payload(*, tenant_id: str, user_id: str, timestamp: str) -> bytes:
    return f"{tenant_id}:{user_id}:{timestamp}".encode("utf-8")


def sign_research_identity(
    secret: str, *, tenant_id: str, user_id: str, timestamp: str
) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        signature_payload(tenant_id=tenant_id, user_id=user_id, timestamp=timestamp),
        hashlib.sha256,
    ).hexdigest()


def get_research_principal(
    x_cavaai_user: str | None = Header(default=None),
    x_cavaai_tenant: str | None = Header(default=None),
    x_cavaai_timestamp: str | None = Header(default=None),
    x_cavaai_signature: str | None = Header(default=None),
) -> ResearchPrincipal | None:
    settings = get_settings()
    required = settings.research_auth_required or settings.app_env.lower() == "production"
    supplied = all(
        [x_cavaai_user, x_cavaai_tenant, x_cavaai_timestamp, x_cavaai_signature]
    )
    if not supplied:
        if required:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="A signed Research OS identity is required",
            )
        return None

    research_auth_secret = settings.research_auth_secret
    if not research_auth_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Research authentication is not configured",
        )

    try:
        issued_at = int(x_cavaai_timestamp or "0")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Research OS identity timestamp",
        ) from exc

    max_age = settings.research_auth_max_age_seconds
    if abs(int(time.time()) - issued_at) > max_age:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Expired Research OS identity",
        )

    expected = sign_research_identity(
        research_auth_secret,
        tenant_id=x_cavaai_tenant or "",
        user_id=x_cavaai_user or "",
        timestamp=x_cavaai_timestamp or "",
    )
    if not hmac.compare_digest(expected, x_cavaai_signature or ""):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Research OS identity signature",
        )

    if not (x_cavaai_user or "").strip() or not (x_cavaai_tenant or "").strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Research OS identity",
        )

    return ResearchPrincipal(
        user_id=(x_cavaai_user or "").strip(),
        tenant_external_id=(x_cavaai_tenant or "").strip(),
    )


def identity_metadata(principal: ResearchPrincipal | None) -> dict:
    if not principal:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "user_id": principal.user_id,
        "tenant_external_id": principal.tenant_external_id,
        "verified_at": datetime.now(UTC).isoformat(),
    }
