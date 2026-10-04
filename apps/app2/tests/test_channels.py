from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import channels


class FakeDB:
    def __init__(self):
        self.added = []
        self.committed = 0

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed += 1

    def refresh(self, obj):
        pass


def test_create_link_code_creates_row_when_missing():
    db = FakeDB()
    db.scalar = MagicMock(return_value=None)
    code = channels.create_link_code(db, 1, "telegram")

    assert len(code) == 6 and code.isdigit()
    assert db.added and db.added[0].channel == "telegram"
    assert db.committed == 1


def test_consume_link_code_success():
    link = SimpleNamespace(
        user_id=1,
        channel="telegram",
        external_user_id=None,
        telegram_username=None,
        code="123456",
        code_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        updated_at=None,
    )
    db = FakeDB()
    db.scalar = MagicMock(return_value=link)

    result = channels.consume_link_code(db, "telegram", "123456", "999", telegram_username="bob")

    assert result is link
    assert link.external_user_id == "999"
    assert link.code is None
    assert link.telegram_username == "bob"


def test_consume_link_code_expired():
    link = SimpleNamespace(
        user_id=1,
        channel="telegram",
        external_user_id=None,
        code="123456",
        code_expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db = FakeDB()
    db.scalar = MagicMock(return_value=link)

    assert channels.consume_link_code(db, "telegram", "123456", "999") is None


def test_consume_link_code_unknown():
    db = FakeDB()
    db.scalar = MagicMock(return_value=None)
    assert channels.consume_link_code(db, "telegram", "000000", "999") is None


@pytest.mark.asyncio
async def test_handle_channel_message_persists_plan_and_logs():
    from app.schemas import AgentResponse

    agent_session = SimpleNamespace(pending_plan=None, updated_at=None)
    db = FakeDB()

    with patch.object(channels, "_get_or_create_agent_session", return_value=agent_session), patch(
        "app.services.conversations.get_or_create_conversation",
        return_value=SimpleNamespace(id=77),
    ), patch(
        "app.services.conversations.get_recent_messages", return_value=[]
    ), patch(
        "app.services.conversations.log_message"
    ) as log_mock, patch(
        "app.agent.runner.process_message",
        AsyncMock(return_value=AgentResponse(message="Confirma?", needs_confirmation=True)),
    ):
        reply = await channels.handle_channel_message(db, 1, "telegram", "999", "gastei 10")

    assert reply.message == "Confirma?"
    assert reply.needs_confirmation is True
    assert agent_session.pending_plan is None  # session had no plan
    assert log_mock.call_count == 2


@pytest.mark.asyncio
async def test_handle_channel_message_survives_runner_error():
    db = FakeDB()
    agent_session = SimpleNamespace(pending_plan=None, updated_at=None)

    with patch.object(channels, "_get_or_create_agent_session", return_value=agent_session), patch(
        "app.services.conversations.get_or_create_conversation",
        return_value=SimpleNamespace(id=1),
    ), patch("app.services.conversations.get_recent_messages", return_value=[]), patch(
        "app.agent.runner.process_message", AsyncMock(side_effect=RuntimeError("boom"))
    ):
        reply = await channels.handle_channel_message(db, 1, "whatsapp", "555", "oi")

    assert "Não consegui processar" in reply.message
