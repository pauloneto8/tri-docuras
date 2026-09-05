import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.agent.runner import process_message
from app.auth import create_user
from app.models import Account, CardInvoice, Category, CreditCard, Transaction, User
from app.schemas import CreateAccountInput, CreateCardInput, ToolCall
from app.services import finance
from app.services.tools import execute_tool, format_tool_result


@pytest.mark.asyncio
async def test_runner_requests_confirmation_for_update_card():
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"runner_card_{suffix}@test.com",
        password="secret1",
        name="Runner User",
        is_active=True,
    )
    session: dict = {}
    try:
        finance.seed_defaults(db, user.id)
        debit = finance.create_account(
            db,
            user.id,
            CreateAccountInput(
                name=f"Corrente_{suffix}",
                account_type="corrente",
                opening_balance="0",
            ),
        )
        card_name = f"Nubank_{suffix}"
        finance.create_card(
            db,
            user.id,
            CreateCardInput(
                name=card_name,
                closing_day=10,
                due_day=17,
                settlement_account_name=debit["name"],
            ),
        )

        tool_call = ToolCall(
            tool="update_card",
            arguments={
                "card_name": card_name,
                "due_day": 20,
            },
        )

        with patch(
            "app.agent.runner.call_intent_llm",
            new=AsyncMock(return_value=(tool_call, "groq")),
        ):
            pending = await process_message(
                db,
                user.id,
                f"Altere o vencimento do cartão {card_name} para dia 20",
                session=session,
            )

        assert pending.needs_confirmation
        assert pending.tool_used == "update_card"
        assert pending.pending_action["tool"] == "update_card"

        outcome = execute_tool(db, user.id, ToolCall(**pending.pending_action))
        message = format_tool_result(outcome["action"], outcome["result"])
        assert "20" in message

        card = db.scalar(
            select(CreditCard).where(
                CreditCard.user_id == user.id,
                CreditCard.name == card_name,
            )
        )
        assert card is not None
        assert card.due_day == 20
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(CardInvoice).filter(CardInvoice.user_id == user.id).delete(synchronize_session=False)
        db.query(CreditCard).filter(CreditCard.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_runner_requests_confirmation_for_delete_card():
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"runner_del_card_{suffix}@test.com",
        password="secret1",
        name="Runner User",
        is_active=True,
    )
    session: dict = {}
    try:
        finance.seed_defaults(db, user.id)
        debit = finance.create_account(
            db,
            user.id,
            CreateAccountInput(
                name=f"Corrente_{suffix}",
                account_type="corrente",
                opening_balance="0",
            ),
        )
        card_name = f"Itaú_{suffix}"
        finance.create_card(
            db,
            user.id,
            CreateCardInput(
                name=card_name,
                closing_day=5,
                due_day=15,
                settlement_account_name=debit["name"],
            ),
        )

        tool_call = ToolCall(
            tool="delete_card",
            arguments={"card_name": card_name},
        )

        with patch(
            "app.agent.runner.call_intent_llm",
            new=AsyncMock(return_value=(tool_call, "groq")),
        ):
            pending = await process_message(
                db,
                user.id,
                f"Excluir cartão {card_name}",
                session=session,
            )

        assert pending.needs_confirmation
        assert pending.tool_used == "delete_card"

        outcome = execute_tool(db, user.id, ToolCall(**pending.pending_action))
        message = format_tool_result(outcome["action"], outcome["result"])
        assert "excluído" in message.lower()

        card = db.scalar(
            select(CreditCard).where(
                CreditCard.user_id == user.id,
                CreditCard.name == card_name,
            )
        )
        assert card is not None
        assert card.is_active is False
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(CardInvoice).filter(CardInvoice.user_id == user.id).delete(synchronize_session=False)
        db.query(CreditCard).filter(CreditCard.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()
