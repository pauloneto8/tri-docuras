"""WhatsApp Cloud API webhook router."""
from __future__ import annotations

import hashlib
import hmac
import logging

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.security.rate_limit import rate_limited

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

_VINCULAR_PREFIXES = ("vincular", "/vincular")


@router.get("/webhook")
@rate_limited("whatsapp_webhook_get")
async def whatsapp_verify(
    hub_mode: str | None = None,
    hub_challenge: str | None = None,
    hub_verify_token: str | None = None,
):
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        return int(hub_challenge) if hub_challenge and hub_challenge.isdigit() else hub_challenge
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid verify token")


@router.post("/webhook")
@rate_limited("whatsapp_webhook_post")
async def whatsapp_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    raw = await request.body()
    if settings.whatsapp_app_secret:
        if not _valid_signature(raw, x_hub_signature_256, settings.whatsapp_app_secret):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid signature")
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        return {"ok": True}

    try:
        await _handle_payload(db, payload)
    except Exception:  # noqa: BLE001 — nunca propaga erro para a Meta (evita retries)
        logger.exception("Falha ao processar webhook do WhatsApp")
    return {"ok": True}


def _valid_signature(raw: bytes, header: str | None, app_secret: str) -> bool:
    if not header:
        return False
    expected = hmac.new(app_secret.encode(), raw, hashlib.sha256).hexdigest()
    provided = header.split("=", 1)[-1]
    return hmac.compare_digest(expected, provided)


async def _handle_payload(db: Session, payload: dict) -> None:
    from app.services import channels

    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for message in value.get("messages") or []:
                await _handle_message(db, message, channels)


async def _handle_message(db, message: dict, channels) -> None:
    from app.services.channels import ChannelReply

    from_number = message.get("from")
    if not from_number:
        return
    from_number = str(from_number)

    text = message.get("text", {}).get("body") if message.get("type") == "text" else None
    if message.get("type") == "interactive":
        reply = (message.get("interactive") or {}).get("button_reply") or {}
        text = {"agent:confirm": "sim", "agent:cancel": "não"}.get(reply.get("id"))
    if not text and message.get("type") == "audio":
        text = await _transcribe_whatsapp_audio(message)

    link = channels.get_link(db, "whatsapp", from_number)
    if link is None:
        await _try_link(db, text or "", from_number, channels)
        return
    if not text:
        return

    result: ChannelReply = await channels.handle_channel_message(
        db, link.user_id, "whatsapp", from_number, text
    )
    await channels.send_whatsapp_message(
        settings.whatsapp_access_token,
        settings.whatsapp_phone_number_id,
        from_number,
        result.message,
        confirm=result.needs_confirmation,
    )


async def _try_link(db, text: str, from_number: str, channels) -> None:
    parts = text.strip().split()
    if parts and parts[0].lower() in _VINCULAR_PREFIXES and len(parts) > 1:
        link = channels.consume_link_code(db, "whatsapp", parts[1], from_number)
        msg = (
            "Conta vinculada! Pode mandar seus lançamentos por aqui."
            if link
            else "Código inválido ou expirado."
        )
    else:
        msg = (
            "Você ainda não vinculou sua conta. No AssistFin, abra "
            "“Conectar WhatsApp” e mande vincular <código>."
        )
    await channels.send_whatsapp_message(
        settings.whatsapp_access_token,
        settings.whatsapp_phone_number_id,
        from_number,
        msg,
    )


async def _transcribe_whatsapp_audio(message: dict) -> str | None:
    from app.services import channels

    media_id = (message.get("audio") or {}).get("id")
    if not media_id or not settings.whatsapp_access_token:
        return None
    headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{channels.WHATSAPP_API}/{media_id}", headers=headers
            )
            resp.raise_for_status()
            url = resp.json().get("url")
        if not url:
            return None
        async with httpx.AsyncClient(timeout=60.0) as client:
            media = await client.get(url, headers=headers)
            media.raise_for_status()
            content = media.content
    except Exception:  # noqa: BLE001
        logger.exception("Falha ao baixar áudio do WhatsApp")
        return None
    return await channels.transcribe_audio(settings.groq_api_key, content, "audio.ogg")
