"""Single-use linking: owner session + authenticated bot relay + owner confirmation."""
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import AlertSubscription, TelegramChatBinding, TelegramLinkChallenge


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def require_owner(db: Session) -> tuple[int, str]:
    tenant, user = db.info.get("tenant_id"), db.info.get("user_id")
    if tenant is None or not user:
        raise HTTPException(401, "Se requiere una identidad verificada")
    return tenant, user


def binding_for(db: Session, tenant: int, user: str, chat_id: str):
    return db.scalar(select(TelegramChatBinding).where(
        TelegramChatBinding.tenant_id == tenant, TelegramChatBinding.user_id == user,
        TelegramChatBinding.chat_id == chat_id))


def start_link(db: Session) -> dict:
    tenant, user = require_owner(db)
    # Invalidate old active challenges on new start; only newest code may link.
    db.execute(update(TelegramLinkChallenge).where(
        TelegramLinkChallenge.tenant_id == tenant, TelegramLinkChallenge.user_id == user,
        TelegramLinkChallenge.confirmed.is_(False)).values(expires_at=datetime.now(UTC)))
    token = secrets.token_urlsafe(32)
    row = TelegramLinkChallenge(tenant_id=tenant, user_id=user,
        token_hash=hashlib.sha256(token.encode()).hexdigest(), expires_at=datetime.now(UTC)+timedelta(minutes=10))
    db.add(row)
    db.commit()
    return {"challenge_id": row.id, "command": f"/link {token}", "expires_at": row.expires_at}


def verify_relay(secret: str | None, body: bytes, timestamp: str, signature: str) -> None:
    if not secret or len(secret) < 32:
        raise HTTPException(503, "Vinculación de Telegram sin configurar")
    try:
        seconds = int(timestamp)
    except ValueError as exc:
        raise HTTPException(401, "Firma de bot no válida") from exc
    if not 0 <= datetime.now(UTC).timestamp()-seconds <= 60:
        raise HTTPException(401, "Firma de bot caducada")
    expected = hmac.new(secret.encode(), timestamp.encode()+b"."+body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(401, "Firma de bot no válida")


def receive_bot_link(db: Session, token: str, chat_id: str) -> None:
    # Called only by authenticated relay endpoint, never an owner-controlled body.
    claimed = db.execute(update(TelegramLinkChallenge).where(
        TelegramLinkChallenge.token_hash == hashlib.sha256(token.encode()).hexdigest(),
        TelegramLinkChallenge.expires_at > datetime.now(UTC),
        TelegramLinkChallenge.candidate_chat_id.is_(None),
        TelegramLinkChallenge.confirmed.is_(False),
    ).values(candidate_chat_id=chat_id).returning(TelegramLinkChallenge.id)).scalar_one_or_none()
    db.commit()
    if claimed is None:
        raise HTTPException(409, "Código de vinculación usado o caducado")


def inspect_link(db: Session, challenge_id: int) -> TelegramLinkChallenge:
    tenant, user = require_owner(db)
    row = db.scalar(select(TelegramLinkChallenge).where(
        TelegramLinkChallenge.id == challenge_id, TelegramLinkChallenge.tenant_id == tenant,
        TelegramLinkChallenge.user_id == user))
    if row is None:
        raise HTTPException(404, "Vinculación no encontrada")
    return row


def confirm_link(db: Session, challenge_id: int, expected_chat_id: str) -> dict:
    row = inspect_link(db, challenge_id)
    if utc(row.expires_at) <= datetime.now(UTC) or not row.candidate_chat_id or row.confirmed:
        raise HTTPException(409, "Vinculación sin prueba del bot, usada o caducada")
    if not hmac.compare_digest(row.candidate_chat_id, expected_chat_id):
        raise HTTPException(403, "El chat no coincide con la prueba del bot")
    claimed = db.execute(update(TelegramLinkChallenge).where(
        TelegramLinkChallenge.id == row.id, TelegramLinkChallenge.confirmed.is_(False),
        TelegramLinkChallenge.expires_at > datetime.now(UTC),
        TelegramLinkChallenge.candidate_chat_id == expected_chat_id,
    ).values(confirmed=True).returning(TelegramLinkChallenge.id)).scalar_one_or_none()
    if claimed is None:
        db.rollback()
        raise HTTPException(409, "Vinculación ya utilizada")
    binding = db.scalar(select(TelegramChatBinding).where(
        TelegramChatBinding.tenant_id == row.tenant_id, TelegramChatBinding.user_id == row.user_id))
    if binding is None:
        db.add(TelegramChatBinding(tenant_id=row.tenant_id, user_id=row.user_id, chat_id=expected_chat_id))
    else:
        binding.chat_id = expected_chat_id
    # Changing/reconfirming destination never silently widens consent.
    db.execute(update(AlertSubscription).where(AlertSubscription.tenant_id == row.tenant_id,
        AlertSubscription.user_id == row.user_id).values(enabled=False))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Chat vinculado a otra identidad") from exc
    return {"chat_id": expected_chat_id, "verified": True}
