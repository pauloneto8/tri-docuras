import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agent.runner import process_message
from app.auth import create_user
from app.config import settings
from app.models import Account, Category, Transaction, User
from app.schemas import ListTransactionsInput, RegisterExpenseInput, ToolCall
from app.services import finance
from app.services.delete_flow import prepare_delete_transaction, try_process_pending_delete
from tests.test_transaction_slots import _create_account, _setup_user


def _create_expense(db, user_id, account_name, amount, description):
    finance.register_expense(
        db,
        user_id,
        RegisterExpenseInput(
            amount=amount,
            description=description,
            account_name=account_name,
            category_name="Transporte",
        ),
    )


@pytest.mark.asyncio
async def test_vague_delete_asks_without_confirmation():
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"del_vague_{suffix}@test.com",
        password="secret1",
        name="Delete User",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        acc = _create_account(db, user.id, f"Conta_{suffix}")
        _create_expense(db, user.id, acc["name"], "40.50", "passagem A")
        _create_expense(db, user.id, acc["name"], "54", "passagem B")

        session = {}
        tool = ToolCall(tool="delete_transaction", arguments={})
        resolved, question = prepare_delete_transaction(db, user.id, tool, session)

        assert resolved is None
        assert question is not None
        assert "Qual lançamento" in question
        assert "pending_delete" in session
        assert len(session["pending_delete"]["candidates"]) == 2
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_ambiguous_amount_asks_both_candidates():
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"del_amb_{suffix}@test.com",
        password="secret1",
        name="Delete User 2",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        acc = _create_account(db, user.id, f"Conta_{suffix}")
        _create_expense(db, user.id, acc["name"], "40.50", "passagem mercado")
        _create_expense(db, user.id, acc["name"], "40.50", "passagem carteira")

        session = {}
        tool = ToolCall(
            tool="delete_transaction",
            arguments={"amount": "40.50"},
        )
        resolved, question = prepare_delete_transaction(db, user.id, tool, session)

        assert resolved is None
        assert "mais de um" in question.lower()
        assert len(session["pending_delete"]["candidates"]) == 2
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_unique_match_goes_to_confirmation():
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"del_unique_{suffix}@test.com",
        password="secret1",
        name="Delete User 3",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        acc = _create_account(db, user.id, f"Conta_{suffix}")
        _create_expense(db, user.id, acc["name"], "40.50", "passagem mercado")
        _create_expense(db, user.id, acc["name"], "54", "uber")

        session = {}
        tool = ToolCall(
            tool="delete_transaction",
            arguments={"amount": "40.50", "description": "passagem"},
        )
        resolved, question = prepare_delete_transaction(db, user.id, tool, session)

        assert question is None
        assert resolved is not None
        assert resolved.tool == "delete_transaction"
        assert resolved.arguments["transaction_id"] is not None
        assert "pending_delete" not in session
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_pending_delete_choice_by_id_confirms():
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"del_pick_{suffix}@test.com",
        password="secret1",
        name="Delete User 4",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        acc = _create_account(db, user.id, f"Conta_{suffix}")
        _create_expense(db, user.id, acc["name"], "40.50", "passagem A")
        _create_expense(db, user.id, acc["name"], "40.50", "passagem B")
        txs = finance.list_transactions(
            db, user.id, ListTransactionsInput(limit=5)
        )
        target_id = txs[0]["id"]

        session = {
            "pending_delete": {
                "candidates": txs,
            }
        }
        result = try_process_pending_delete(session, str(target_id), db, user.id)

        assert result is not None
        assert result.needs_confirmation is True
        assert result.pending_action["arguments"]["transaction_id"] == target_id
        assert "pending_delete" not in session
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_delete_requires_transaction_id():
    from app.schemas import DeleteTransactionInput

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"del_req_{suffix}@test.com",
        password="secret1",
        name="Delete User 5",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        with pytest.raises(ValueError, match="obrigatório"):
            finance.delete_transaction(
                db,
                user.id,
                DeleteTransactionInput(amount="40.50"),
            )
    finally:
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_runner_vague_delete_does_not_confirm_immediately():
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"del_run_{suffix}@test.com",
        password="secret1",
        name="Delete User 6",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        acc = _create_account(db, user.id, f"Conta_{suffix}")
        _create_expense(db, user.id, acc["name"], "40.50", "passagem")

        session = {}
        tool = ToolCall(tool="delete_transaction", arguments={})
        with patch(
            "app.agent.runner.call_intent_llm",
            new_callable=AsyncMock,
            return_value=(tool, "groq"),
        ):
            result = await process_message(
                db, user.id, "Exclua um lançamento", session=session
            )

        assert result.needs_confirmation is False
        assert "Qual lançamento" in result.message
        assert "pending_delete" in session
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()
