import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.auth import create_user
from app.models import Account, Category, Transaction, User
from app.schemas import CreateAccountInput, ToolCall
from app.services import finance
from app.services.transaction_slots import (
    ensure_transaction_slots,
    infer_account_name,
    infer_category_name,
    process_slot_answer,
    resolve_transaction_date,
)
from app.timezone import local_today
from tests.wizard_helpers import decline_recurring_slot


def _setup_user(db, user):
    finance.seed_defaults(db, user.id)


def _create_account(db, user_id, name, **kwargs):
    return finance.create_account(
        db,
        user_id,
        CreateAccountInput(name=name, account_type="corrente", **kwargs),
    )


def test_resolve_transaction_date_prefers_ontem_over_explicit_today():
    from datetime import timedelta

    from app.timezone import local_today

    message = "gastei 40 de passagens ontem"
    explicit = local_today().isoformat()
    resolved = resolve_transaction_date(message, explicit)
    assert resolved == (local_today() - timedelta(days=1)).isoformat()


@pytest.mark.asyncio
async def test_passagens_suggests_transporte_category():
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"slots_{suffix}@test.com",
        password="secret1",
        name="Slots User",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        category = infer_category_name(db, user.id, "passagens", "expense")
        assert category == "Transporte"
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_two_accounts_asks_account_one_account_auto():
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"slots2_{suffix}@test.com",
        password="secret1",
        name="Slots User 2",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        _create_account(db, user.id, f"Carteira_{suffix}")
        _create_account(db, user.id, f"Mercado_{suffix}")

        message = "Hoje eu gastei r$ 40,50 de passagens"
        assert infer_account_name(db, user.id, message) is None

        session = {}
        tool_call = ToolCall(
            tool="register_expense",
            arguments={
                "amount": "40.50",
                "description": "passagens",
                "transaction_date": "2026-08-30",
            },
        )
        result = ensure_transaction_slots(db, user.id, session, tool_call, message)
        assert result.question is not None
        assert "realizado" in result.question.lower() or "previsão" in result.question.lower() or "previsto" in result.question.lower()
        assert session["transaction_wizard"]["status"] is None

        status_slot = process_slot_answer(db, user.id, session, "realizado")
        status_slot = decline_recurring_slot(session, db, user.id) or status_slot
        assert status_slot.question is not None
        assert "conta" in status_slot.question.lower()
        assert session["transaction_wizard"]["category_name"] == "Transporte"

        slot = process_slot_answer(db, user.id, session, f"Mercado_{suffix}")
        assert slot.tool_call is not None
        assert slot.tool_call.arguments["account_name"] == f"Mercado_{suffix}"
        assert slot.tool_call.arguments["category_name"] == "Transporte"
        assert slot.tool_call.arguments["status"] == "actual"
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_ontem_preserves_yesterday_date_through_account_slot():
    from datetime import date, timedelta

    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"slots_ontem_{suffix}@test.com",
        password="secret1",
        name="Slots Ontem",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        _create_account(db, user.id, f"Carteira_{suffix}")
        _create_account(db, user.id, f"Mercado_{suffix}")

        message = "Ontem gastei 40,50 de passagens para cidade de Timbaúba"
        tool_call = ToolCall(
            tool="register_expense",
            arguments={
                "amount": "40,50",
                "description": "passagens para cidade de Timbaúba",
            },
        )
        session = {}
        result = ensure_transaction_slots(db, user.id, session, tool_call, message)
        assert result.question is not None
        assert session["transaction_wizard"]["transaction_date"] == (
            date.today() - timedelta(days=1)
        ).isoformat()
        assert "realizado" in result.question.lower() or "previsto" in result.question.lower()

        status_slot = process_slot_answer(db, user.id, session, "realizado")
        status_slot = decline_recurring_slot(session, db, user.id) or status_slot
        assert status_slot.question is not None

        slot = process_slot_answer(db, user.id, session, f"Mercado_{suffix}")
        assert slot.tool_call is not None
        assert slot.tool_call.arguments["transaction_date"] == (
            date.today() - timedelta(days=1)
        ).isoformat()
        assert slot.tool_call.arguments["status"] == "actual"
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        assert slot.tool_call.arguments["payment_date"] == yesterday
        assert slot.tool_call.arguments["competence_date"] == yesterday
        assert slot.tool_call.arguments["due_date"] == yesterday
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_single_account_auto_fills():
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"slots3_{suffix}@test.com",
        password="secret1",
        name="Slots User 3",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        _create_account(db, user.id, f"Nubank_{suffix}")

        message = "gastei 40,50 de passagens"
        session = {}
        tool_call = ToolCall(
            tool="register_expense",
            arguments={"amount": "40.50", "description": "passagens"},
        )
        result = ensure_transaction_slots(db, user.id, session, tool_call, message)
        assert result.question is not None
        assert "realizado" in result.question.lower() or "previsto" in result.question.lower()
        assert result.tool_call is None

        filled = process_slot_answer(db, user.id, session, "realizado")
        assert filled.question is not None
        assert "realização" in filled.question.lower() or "realizacao" in filled.question.lower()
        filled = process_slot_answer(db, user.id, session, "hoje")
        filled = decline_recurring_slot(session, db, user.id) or filled
        assert filled.tool_call is not None
        assert filled.tool_call.arguments["account_name"] == f"Nubank_{suffix}"
        assert filled.tool_call.arguments["category_name"] == "Transporte"
        assert filled.tool_call.arguments["status"] == "actual"
        today = local_today().isoformat()
        assert filled.tool_call.arguments["payment_date"] == today
        assert filled.tool_call.arguments["competence_date"] == today
        assert filled.tool_call.arguments["due_date"] == today
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_register_expense_without_amount_asks_value():
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"slots_value_{suffix}@test.com",
        password="secret1",
        name="Slots Value",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        session = {}
        tool_call = ToolCall(tool="register_expense", arguments={})
        result = ensure_transaction_slots(
            db, user.id, session, tool_call, "Quero lançar uma despesa"
        )
        assert result.question is not None
        assert "realizado" in result.question.lower() or "previsto" in result.question.lower()
        assert session["transaction_wizard"]["tx_type"] == "expense"
        assert session["transaction_wizard"]["status"] is None
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_runner_starts_expense_flow_without_amount():
    from app.agent.runner import process_message
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"runner_expense_{suffix}@test.com",
        password="secret1",
        name="Runner Expense",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        session = {}
        result = await process_message(
            db, user.id, "Quero lançar uma despesa", session=session
        )
        assert "realizado" in result.message.lower() or "previsto" in result.message.lower()
        assert result.source == "rule"
        assert session["transaction_wizard"]["tx_type"] == "expense"
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_runner_asks_account_for_passagens_with_two_accounts():
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.agent.runner import process_message
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"slots4_{suffix}@test.com",
        password="secret1",
        name="Slots User 4",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        _create_account(db, user.id, f"Carteira_{suffix}")
        _create_account(db, user.id, f"Mercado_{suffix}")

        session = {}
        message = "Hoje eu gastei r$ 40,50 de passagens"
        result = await process_message(db, user.id, message, session=session)
        assert "realizado" in result.message.lower() or "previsto" in result.message.lower()

        result_status = await process_message(db, user.id, "realizado", session=session)
        if "fixo" in result_status.message.lower():
            result_status = await process_message(db, user.id, "Não", session=session)
        assert "conta" in result_status.message.lower()
        assert "Transporte" in result_status.message or session["transaction_wizard"]["category_name"] == "Transporte"

        result2 = await process_message(db, user.id, f"Mercado_{suffix}", session=session)
        assert result2.needs_confirmation
        assert result2.pending_action["arguments"]["account_name"] == f"Mercado_{suffix}"
        assert result2.pending_action["arguments"]["category_name"] == "Transporte"
        assert result2.pending_action["arguments"]["status"] == "actual"
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_planned_slots_ask_competence_then_due():
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"slots_planned_{suffix}@test.com",
        password="secret1",
        name="Slots Planned",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        _create_account(db, user.id, f"Conta_{suffix}")
        session = {}
        tool_call = ToolCall(
            tool="register_expense",
            arguments={"amount": "200", "description": "aluguel"},
        )
        result = ensure_transaction_slots(
            db, user.id, session, tool_call, "Quero lançar previsão de aluguel"
        )
        assert result.question is not None

        status_slot = process_slot_answer(db, user.id, session, "previsto")
        assert status_slot.question is not None
        assert "competência" in status_slot.question.lower() or "competencia" in status_slot.question.lower()

        comp_slot = process_slot_answer(db, user.id, session, "01/08/2026")
        assert comp_slot.question is not None
        assert "vencimento" in comp_slot.question.lower()
        assert session["transaction_wizard"]["competence_date"] == "2026-08-01"

        due_slot = process_slot_answer(db, user.id, session, "10/08/2026")
        assert due_slot.question is not None
        assert "fixo" in due_slot.question.lower() or "recorr" in due_slot.question.lower()

        recur_slot = process_slot_answer(db, user.id, session, "Não")
        assert recur_slot.tool_call is not None
        args = recur_slot.tool_call.arguments
        assert args["status"] == "planned"
        assert args["competence_date"] == "2026-08-01"
        assert args["due_date"] == "2026-08-10"
        assert not args.get("payment_date")
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()
