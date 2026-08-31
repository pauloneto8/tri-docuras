import uuid

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.auth import create_user
from app.models import Category, Conversation, ConversationMessage, User
from app.services.conversations import get_or_create_conversation, log_message, list_conversations


def test_log_conversation_messages():
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"conv_{suffix}@example.com",
        password="secret1",
        name="Conv User",
        is_active=True,
    )
    session = {}
    try:
        conv = get_or_create_conversation(db, user.id, session)
        log_message(
            db,
            conversation_id=conv.id,
            user_id=user.id,
            role="user",
            content="cadastrar conta",
            source="wizard",
        )
        log_message(
            db,
            conversation_id=conv.id,
            user_id=user.id,
            role="assistant",
            content="Qual o apelido da conta?",
            source="wizard",
            metadata={"wizard_active": True},
        )
        messages = db.scalars(
            select(ConversationMessage).where(ConversationMessage.conversation_id == conv.id)
        ).all()
        assert len(messages) == 2
        convs = list_conversations(db, user.id)
        assert any(c.id == conv.id for c in convs)
    finally:
        db.query(ConversationMessage).filter(ConversationMessage.user_id == user.id).delete(
            synchronize_session=False
        )
        db.query(Conversation).filter(Conversation.user_id == user.id).delete(
            synchronize_session=False
        )
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()
