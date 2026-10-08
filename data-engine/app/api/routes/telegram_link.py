"""Private owner linking routes and separately HMAC-authenticated Asistenta relay."""
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.database import SessionLocal, get_db
from app.services import telegram_link as service

router = APIRouter()
relay_router = APIRouter()


class LinkStartOut(BaseModel):
    challenge_id: int
    command: str
    expires_at: str


class LinkStatusOut(BaseModel):
    chat_id: str | None
    confirmed: bool


class LinkConfirmIn(BaseModel):
    chat_id: str = Field(pattern=r"^[1-9][0-9]{0,19}$")


class LinkConfirmOut(BaseModel):
    chat_id: str
    verified: bool


class BotLinkIn(BaseModel):
    token: str = Field(min_length=40, max_length=64)
    chat_id: str = Field(pattern=r"^[1-9][0-9]{0,19}$")
    telegram_user_id: str = Field(pattern=r"^[1-9][0-9]{0,19}$")
    chat_type: str


@router.post("/telegram-link", response_model=LinkStartOut)
def start(db=Depends(get_db)):
    result = service.start_link(db)
    result["expires_at"] = result["expires_at"].isoformat()
    return result


@router.get("/telegram-link/{challenge_id}", response_model=LinkStatusOut)
def status(challenge_id: int, db=Depends(get_db)):
    row = service.inspect_link(db, challenge_id)
    return {"chat_id": row.candidate_chat_id, "confirmed": row.confirmed}


@router.post("/telegram-link/{challenge_id}/confirm", response_model=LinkConfirmOut)
def confirm(challenge_id: int, payload: LinkConfirmIn, db=Depends(get_db)):
    return service.confirm_link(db, challenge_id, payload.chat_id)


@relay_router.post("/api/telegram/link-proof")
async def relay(
    request: Request,
    payload: BotLinkIn,
    x_asistenta_timestamp: str = Header(default=""),
    x_asistenta_signature: str = Header(default=""),
):
    # Separate from owner auth: only the bot server knows the shared secret.
    service.verify_relay(get_settings().telegram_link_secret, await request.body(),
                         x_asistenta_timestamp, x_asistenta_signature)
    if payload.chat_type != "private" or payload.chat_id != payload.telegram_user_id:
        raise HTTPException(403, "Se requiere el chat privado del usuario del bot")
    with SessionLocal() as db:
        service.receive_bot_link(db, payload.token, payload.chat_id)
    return {"status": "received"}
