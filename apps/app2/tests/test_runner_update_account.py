import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.agent.runner import process_message
from app.auth import create_user
from app.models import Account, Category, User
from app.schemas import CreateAccountInput, ToolCall
from app.services import finance
from app.services.tools import execute_tool, format_tool_result


@pytest.mark.asyncio
async def test_runner_requests_confirmation_for_update_account():
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"runner_acc_{suffix}@test.com",
        password="secret1",
        name="Runner User",
        is_active=True,
    )
    session: dict = {}
    try:
        finance.seed_defaults(db, user.id)
        finance.create_account(
            db,
            user.id,
            CreateAccountInput(
                name="Mercado Pago",
                account_type="corrente",
                institution="Mercado Pago",
                opening_balance="0",
            ),
        )

        tool_call = ToolCall(
            tool="update_account",
            arguments={
                "account_name": "Mercado Pago",
                "opening_balance": "889,63",
            },
        )

        with patch(
            "app.agent.runner.call_intent_llm",
            new=AsyncMock(return_value=(tool_call, "groq")),
        ):
            pending = await process_message(
                db,
                user.id,
                "A conta Mercado Pago tem saldo inicial de 889,63. Altere",
                session=session,
            )

        assert pending.needs_confirmation
        assert pending.tool_used == "update_account"
        assert pending.pending_action["tool"] == "update_account"

        outcome = execute_tool(db, user.id, ToolCall(**pending.pending_action))
        message = format_tool_result(outcome["action"], outcome["result"])
        assert "889" in message

        account = db.scalar(
            select(Account).where(
                Account.user_id == user.id,
                Account.name == "Mercado Pago",
            )
        )
        assert account is not None
        assert account.opening_balance_cents == 88963
    finally:
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()
