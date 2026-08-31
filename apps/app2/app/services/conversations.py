import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Conversation, ConversationMessage

SESSION_CONVERSATION_KEY = "chat_conversation_id"
SESSION_CHAT_KEY = "chat_session_key"


def ensure_chat_session(session: dict) -> str:
    key = session.get(SESSION_CHAT_KEY)
    if not key:
        key = uuid.uuid4().hex
        session[SESSION_CHAT_KEY] = key
    return key


def get_or_create_conversation(db: Session, user_id: int, session: dict) -> Conversation:
    session_key = ensure_chat_session(session)
    conv_id = session.get(SESSION_CONVERSATION_KEY)
    if conv_id:
        conversation = db.get(Conversation, conv_id)
        if conversation and conversation.user_id == user_id:
            return conversation

    conversation = db.scalar(
        select(Conversation).where(
            Conversation.user_id == user_id,
            Conversation.session_key == session_key,
        )
    )
    if not conversation:
        conversation = Conversation(user_id=user_id, session_key=session_key)
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    session[SESSION_CONVERSATION_KEY] = conversation.id
    return conversation


def log_message(
    db: Session,
    *,
    conversation_id: int,
    user_id: int,
    role: str,
    content: str,
    tool_used: str | None = None,
    source: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> ConversationMessage:
    message = ConversationMessage(
        conversation_id=conversation_id,
        user_id=user_id,
        role=role,
        content=content,
        tool_used=tool_used,
        source=source,
        metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else None,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def list_conversations(db: Session, user_id: int, limit: int = 50) -> list[Conversation]:
    return list(
        db.scalars(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
        )
    )


def get_conversation_messages(
    db: Session, user_id: int, conversation_id: int
) -> list[ConversationMessage]:
    return list(
        db.scalars(
            select(ConversationMessage)
            .join(Conversation)
            .where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
            .order_by(ConversationMessage.created_at)
        )
    )


def get_recent_messages(
    db: Session, user_id: int, conversation_id: int, *, limit: int = 4
) -> list[ConversationMessage]:
    rows = list(
        db.scalars(
            select(ConversationMessage)
            .join(Conversation)
            .where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
            .order_by(ConversationMessage.created_at.desc())
            .limit(limit)
        )
    )
    rows.reverse()
    return rows
