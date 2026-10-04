"""Canais externos (Telegram/WhatsApp): vínculo, sessão e envio.

Reaproveita o runner/agente v2 sem duplicar lógica. Toda consulta é por
`user_id` do vínculo; mensagem de chat não vinculado não acessa nada.
"""
from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AgentSession, UserChannelLink, utcnow_naive
from app.timezone import local_now

logger = logging.getLogger(__name__)

LINK_CODE_TTL_MINUTES = 10
TELEGRAM_API = "https://api.telegram.org"
WHATSAPP_API = "https://graph.facebook.com/v20.0"
GROQ_WHISPER_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
WHISPER_MODEL = "whisper-large-v3-turbo"


@dataclass
class ChannelReply:
    message: str
    needs_confirmation: bool = False
    tool_used: str | None = None
    source: str | None = None


# --- Vínculo de conta ----------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def create_link_code(db: Session, user_id: int, channel: str) -> str:
    link = db.scalar(
        select(UserChannelLink).where(
            UserChannelLink.user_id == user_id,
            UserChannelLink.channel == channel,
        )
    )
    if link is None:
        link = UserChannelLink(user_id=user_id, channel=channel)
        db.add(link)
    code = f"{secrets.randbelow(1_000_000):06d}"
    link.code = code
    link.code_expires_at = _now_utc() + timedelta(minutes=LINK_CODE_TTL_MINUTES)
    db.commit()
    db.refresh(link)
    return code


def consume_link_code(
    db: Session,
    channel: str,
    code: str,
    external_user_id: str,
    *,
    telegram_username: str | None = None,
) -> UserChannelLink | None:
    link = db.scalar(
        select(UserChannelLink).where(
            UserChannelLink.channel == channel,
            UserChannelLink.code == code.strip(),
        )
    )
    if link is None:
        return None
    expires = link.code_expires_at
    if expires is not None:
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < _now_utc():
            return None
    link.external_user_id = str(external_user_id)
    link.telegram_username = telegram_username
    link.code = None
    link.code_expires_at = None
    link.updated_at = _now_utc().replace(tzinfo=None)
    db.commit()
    db.refresh(link)
    return link


def get_link(db: Session, channel: str, external_user_id: str) -> UserChannelLink | None:
    return db.scalar(
        select(UserChannelLink).where(
            UserChannelLink.channel == channel,
            UserChannelLink.external_user_id == str(external_user_id),
        )
    )


# --- Sessão por canal ----------------------------------------------------

def _get_or_create_agent_session(
    db: Session, user_id: int, channel: str, external_chat_id: str
) -> AgentSession:
    row = db.scalar(
        select(AgentSession).where(
            AgentSession.user_id == user_id,
            AgentSession.channel == channel,
            AgentSession.external_chat_id == str(external_chat_id),
        )
    )
    if row is None:
        row = AgentSession(
            user_id=user_id, channel=channel, external_chat_id=str(external_chat_id)
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _history(db: Session, user_id: int, conversation_id: int) -> list[dict]:
    from app.services.conversations import get_recent_messages

    rows = get_recent_messages(db, user_id, conversation_id, limit=12)
    return [{"role": m.role, "content": m.content} for m in rows]


async def handle_channel_message(
    db: Session,
    user_id: int,
    channel: str,
    external_chat_id: str,
    text: str,
) -> ChannelReply:
    from app.agent.runner import process_message
    from app.services.conversations import get_or_create_conversation, log_message

    session: dict[str, Any] = {"chat_session_key": f"{channel}:{external_chat_id}"}
    agent_session = _get_or_create_agent_session(db, user_id, channel, external_chat_id)
    if agent_session.pending_plan:
        session["agent_v2_plan"] = agent_session.pending_plan

    conversation = get_or_create_conversation(db, user_id, session)
    history = _history(db, user_id, conversation.id)

    try:
        result = await process_message(
            db, user_id, text, session=session, history=history
        )
    except Exception:  # noqa: BLE001 — devolve erro amigável ao canal
        logger.exception("Falha ao processar mensagem do canal (user_id=%s)", user_id)
        return ChannelReply(
            message="Não consegui processar sua mensagem agora. Tente novamente."
        )

    plan = session.get("agent_v2_plan")
    agent_session.pending_plan = plan
    agent_session.updated_at = utcnow_naive()
    db.commit()

    log_message(
        db,
        conversation_id=conversation.id,
        user_id=user_id,
        role="user",
        content=text,
        source=f"channel:{channel}",
    )
    log_message(
        db,
        conversation_id=conversation.id,
        user_id=user_id,
        role="assistant",
        content=result.message,
        tool_used=result.tool_used,
        source=result.source or f"channel:{channel}",
        metadata={"needs_confirmation": True} if result.needs_confirmation else None,
    )
    return ChannelReply(
        message=result.message,
        needs_confirmation=result.needs_confirmation,
        tool_used=result.tool_used,
        source=result.source,
    )


# --- Telegram ------------------------------------------------------------

async def send_telegram_message(
    token: str,
    chat_id: str,
    text: str,
    *,
    confirm: bool = False,
) -> bool:
    if not token:
        return False
    payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
    if confirm:
        payload["reply_markup"] = {
            "inline_keyboard": [
                [
                    {"text": "✅ Confirmar", "callback_data": "agent:confirm"},
                    {"text": "❌ Cancelar", "callback_data": "agent:cancel"},
                ]
            ]
        }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{TELEGRAM_API}/bot{token}/sendMessage", json=payload)
            resp.raise_for_status()
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Falha ao enviar mensagem no Telegram")
        return False


async def telegram_get_file_url(token: str, file_id: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{TELEGRAM_API}/bot{token}/getFile", params={"file_id": file_id}
            )
            resp.raise_for_status()
            file_path = resp.json().get("result", {}).get("file_path")
        if not file_path:
            return None
        return f"{TELEGRAM_API}/file/bot{token}/{file_path}"
    except Exception:  # noqa: BLE001
        logger.exception("Falha ao obter arquivo do Telegram")
        return None


async def transcribe_audio(api_key: str, audio_bytes: bytes, filename: str = "audio.ogg") -> str | None:
    if not api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                GROQ_WHISPER_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (filename, audio_bytes)},
                data={"model": WHISPER_MODEL, "language": "pt"},
            )
            resp.raise_for_status()
        return (resp.json().get("text") or "").strip() or None
    except Exception:  # noqa: BLE001
        logger.exception("Falha ao transcrever áudio")
        return None


async def download_bytes(url: str) -> bytes | None:
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content
    except Exception:  # noqa: BLE001
        logger.exception("Falha ao baixar arquivo")
        return None


# --- WhatsApp ------------------------------------------------------------

async def send_whatsapp_message(
    token: str, phone_number_id: str, to: str, text: str, *, confirm: bool = False
) -> bool:
    if not token or not phone_number_id:
        return False
    payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    if confirm:
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": text[:1024]},
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {"id": "agent:confirm", "title": "Confirmar"},
                        },
                        {
                            "type": "reply",
                            "reply": {"id": "agent:cancel", "title": "Cancelar"},
                        },
                    ]
                },
            },
        }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{WHATSAPP_API}/{phone_number_id}/messages",
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
            )
            resp.raise_for_status()
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Falha ao enviar mensagem no WhatsApp")
        return False
