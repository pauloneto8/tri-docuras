"""Telegram webhook router."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.security.rate_limit import rate_limited

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["telegram"])

_VINCULAR_PREFIXES = ("/vincular", "/start")


@router.post("/webhook/{secret}")
@rate_limited("telegram_webhook")
async def telegram_webhook(
    secret: str,
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    expected = settings.telegram_webhook_secret or settings.telegram_bot_token
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="not configured"
        )
    if secret != expected and x_telegram_bot_api_secret_token != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")

    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        return {"ok": True}

    try:
        await _handle_update(db, payload)
    except Exception:  # noqa: BLE001 — nunca propagar erro para o Telegram (evita retries)
        logger.exception("Falha ao processar update do Telegram")
    return {"ok": True}


async def _handle_update(db: Session, payload: dict) -> None:
    from app.services import channels
    from app.services.channels import ChannelReply

    token = settings.telegram_bot_token
    callback = payload.get("callback_query")
    if callback:
        await _handle_callback(db, callback, token)
        return

    message = payload.get("message") or payload.get("edited_message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    from_user = message.get("from") or {}
    if chat_id is None:
        return
    chat_id = str(chat_id)

    text = message.get("text")
    if not text and message.get("voice"):
        text = await _transcribe_telegram_voice(message)
    if not text:
        return

    link = channels.get_link(db, "telegram", chat_id)
    if link is None:
        reply = await _try_link(db, text, chat_id, from_user, token)
        if reply is None:
            await channels.send_telegram_message(
                token,
                chat_id,
                "Você ainda não vinculou sua conta. No AssistFin, abra "
                "“Conectar Telegram” e envie /vincular <código>.",
            )
        return

    result: ChannelReply = await channels.handle_channel_message(
        db, link.user_id, "telegram", chat_id, text
    )
    await channels.send_telegram_message(
        token, chat_id, result.message, confirm=result.needs_confirmation
    )


async def _try_link(db, text, chat_id, from_user, token) -> str | None:
    from app.services import channels

    parts = text.strip().split()
    if not parts or parts[0].lower() not in _VINCULAR_PREFIXES:
        return None
    code = parts[1] if len(parts) > 1 else ""
    if not code:
        return "Envie /vincular <código> com o código gerado no AssistFin."
    link = channels.consume_link_code(
        db,
        "telegram",
        code,
        chat_id,
        telegram_username=from_user.get("username"),
    )
    if link is None:
        await channels.send_telegram_message(token, chat_id, "Código inválido ou expirado.")
    else:
        await channels.send_telegram_message(
            token, chat_id, "Conta vinculada! Pode mandar seus lançamentos por aqui."
        )
    return "linked"


async def _handle_callback(db, callback, token) -> None:
    from app.services import channels

    data = callback.get("data") or ""
    message = callback.get("message") or {}
    chat_id = str((message.get("chat") or {}).get("id") or "")
    if not chat_id:
        return
    link = channels.get_link(db, "telegram", chat_id)
    if link is None:
        return
    if data == "agent:confirm":
        text = "sim"
    elif data == "agent:cancel":
        text = "não"
    else:
        return
    result = await channels.handle_channel_message(
        db, link.user_id, "telegram", chat_id, text
    )
    await channels.send_telegram_message(token, chat_id, result.message)


async def _transcribe_telegram_voice(message) -> str | None:
    from app.services import channels

    voice = message.get("voice") or {}
    file_id = voice.get("file_id")
    if not file_id:
        return None
    url = await channels.telegram_get_file_url(settings.telegram_bot_token, file_id)
    if not url:
        return None
    content = await channels.download_bytes(url)
    if not content:
        return None
    return await channels.transcribe_audio(settings.groq_api_key, content, "voice.ogg")
