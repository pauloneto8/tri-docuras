import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.auth import create_user
from app.models import Account, Category, Transaction, User
from app.schemas import CreateAccountInput, CreateCardInput, ToolCall
from app.services import finance
from app.services.transaction_slots import (
    ensure_transaction_slots,
    infer_account_name,
    infer_card_name,
    infer_category_name,
    parse_slot_date,
    process_slot_answer,
    resolve_transaction_date,
    wants_card_payment,
)
from app.services.transaction_wizard import try_process_transaction_wizard
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
        status_slot = process_slot_answer(db, user.id, session, "hoje") or status_slot
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
        status_slot = process_slot_answer(db, user.id, session, "ontem") or status_slot
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
        assert (
            "único" in filled.question.lower()
            or "unico" in filled.question.lower()
            or "parcelado" in filled.question.lower()
        )
        filled = decline_recurring_slot(session, db, user.id) or filled
        filled = process_slot_answer(db, user.id, session, "hoje")
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
        if any(
            word in result_status.message.lower()
            for word in ("único", "unico", "fixo", "parcelado")
        ):
            result_status = await process_message(db, user.id, "Único", session=session)
        if "realização" in result_status.message.lower() or "realizacao" in result_status.message.lower():
            result_status = await process_message(db, user.id, "hoje", session=session)
        elif "fixo" in result_status.message.lower():
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


def test_parse_slot_date_tambem_copies_competence():
    wizard = {"competence_date": "2026-09-01"}
    assert parse_slot_date("também", wizard, slot="due_date") == "2026-09-01"
    assert parse_slot_date("Também 01/09/2026", wizard, slot="due_date") == "2026-09-01"
    assert parse_slot_date("mesma data", wizard, slot="due_date") == "2026-09-01"


@pytest.mark.asyncio
async def test_planned_installment_reuses_dates_without_reasking():
    from app.config import settings
    from app.services.transaction_wizard import begin_login_prompt

    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"reuse_dates_{suffix}@test.com",
        password="secret1",
        name="Reuse Dates",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        _create_account(db, user.id, f"Flash_{suffix}")
        session = {}
        begin_login_prompt(session)
        try_process_transaction_wizard(session, "receita", db=db, user_id=user.id)
        try_process_transaction_wizard(session, "previsto", db=db, user_id=user.id)
        try_process_transaction_wizard(session, "01/09/2026", db=db, user_id=user.id)
        try_process_transaction_wizard(session, "também", db=db, user_id=user.id)
        try_process_transaction_wizard(session, "parcelado", db=db, user_id=user.id)
        try_process_transaction_wizard(session, "12", db=db, user_id=user.id)
        try_process_transaction_wizard(session, "mensal", db=db, user_id=user.id)
        result = try_process_transaction_wizard(session, "9", db=db, user_id=user.id)
        wizard = session["transaction_wizard"]
        assert wizard["competence_date"] == "2026-09-01"
        assert wizard["due_date"] == "2026-09-01"
        assert result is not None
        assert "competência" not in (result.message or "").lower()
        assert "vencimento" not in (result.message or "").lower()
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(
            synchronize_session=False
        )
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_card_payment_infers_card_not_account_when_names_match():
    from app.config import settings
    from app.models import CreditCard, CardInvoice

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"slots_card_{suffix}@test.com",
        password="secret1",
        name="Card Slots",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        account_name = f"Mercado Pago_{suffix}"
        card_name = f"Mercado Pago_{suffix}"
        _create_account(db, user.id, account_name)
        finance.create_card(
            db,
            user.id,
            CreateCardInput(
                name=card_name,
                closing_day=9,
                due_day=14,
                settlement_account_name=account_name,
            ),
        )
        message = (
            "R$ 17,54 referente a camisa de amigo secreto "
            "lançado no cartão do mercado pago"
        )
        assert wants_card_payment(message)
        assert infer_card_name(db, user.id, message) == card_name
        assert infer_account_name(db, user.id, message) == account_name

        session = {}
        tool_call = ToolCall(
            tool="register_expense",
            arguments={
                "amount": "17.54",
                "description": "camisa de amigo secreto",
            },
        )
        result = ensure_transaction_slots(db, user.id, session, tool_call, message)
        wizard = session["transaction_wizard"]
        assert wizard.get("card_name") is None
        assert wizard.get("payment_source") is None
        assert result.question is not None
        assert "cartão" in result.question.lower()
        assert "conta" in result.question.lower()

        after_card = process_slot_answer(db, user.id, session, "cartão")
        assert after_card.tool_call is not None or after_card.question is not None
        if after_card.tool_call:
            assert after_card.tool_call.arguments["status"] == "planned"
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
async def test_installment_planned_on_card_uses_card_name_in_tool_call():
    from app.config import settings
    from app.models import CreditCard, CardInvoice

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"slots_inst_card_{suffix}@test.com",
        password="secret1",
        name="Inst Card Slots",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        account_name = f"Mercado Pago_{suffix}"
        card_name = f"Mercado Pago_{suffix}"
        _create_account(db, user.id, account_name)
        finance.create_card(
            db,
            user.id,
            CreateCardInput(
                name=card_name,
                closing_day=9,
                due_day=14,
                settlement_account_name=account_name,
            ),
        )
        message = (
            "R$ 17,54 camisa amigo secreto lançado no cartão do mercado pago"
        )
        session = {}
        tool_call = ToolCall(
            tool="register_expense",
            arguments={
                "amount": "17.54",
                "description": "camisa amigo secreto",
            },
        )
        ensure_transaction_slots(db, user.id, session, tool_call, message)

        process_slot_answer(db, user.id, session, "previsto")
        process_slot_answer(db, user.id, session, "cartão")
        process_slot_answer(db, user.id, session, card_name)
        process_slot_answer(db, user.id, session, "15/09/2026")
        process_slot_answer(db, user.id, session, "parcelado")
        process_slot_answer(db, user.id, session, "10")
        process_slot_answer(db, user.id, session, "mensal")
        process_slot_answer(db, user.id, session, "10")
        process_slot_answer(db, user.id, session, "15/09/2026")
        process_slot_answer(db, user.id, session, "17.54")
        process_slot_answer(db, user.id, session, "valor da parcela")
        process_slot_answer(db, user.id, session, "camisa amigo secreto")

        wizard = session["transaction_wizard"]
        assert wizard.get("card_name") == card_name
        assert wizard.get("account_name") == account_name

        slot = process_slot_answer(db, user.id, session, "Outros")
        assert slot.tool_call is not None
        args = slot.tool_call.arguments
        assert args.get("card_name") == card_name
        assert args.get("account_name") == account_name
        assert args.get("installment_count") == 10
        assert args.get("installment_start_index") == 10
        assert args.get("status") == "planned"
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
async def test_card_installment_skips_due_date_and_uses_invoice_due():
    from app.config import settings
    from app.models import CardInvoice, CreditCard

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"slots_card_due_{suffix}@test.com",
        password="secret1",
        name="Card Due Slots",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        account_name = f"Mercado Pago_{suffix}"
        card_name = f"Mercado Pago_{suffix}"
        _create_account(db, user.id, account_name)
        finance.create_card(
            db,
            user.id,
            CreateCardInput(
                name=card_name,
                closing_day=9,
                due_day=14,
                settlement_account_name=account_name,
            ),
        )
        message = (
            "Lance no cartão mercado pago a despesa de 17,47 referente ao presente de amigo secreto"
        )
        session = {}
        tool_call = ToolCall(
            tool="register_expense",
            arguments={"amount": "17.47", "description": "presente amigo secreto"},
        )
        ensure_transaction_slots(db, user.id, session, tool_call, message)

        process_slot_answer(db, user.id, session, "realizado")
        process_slot_answer(db, user.id, session, "cartão")
        process_slot_answer(db, user.id, session, card_name)
        process_slot_answer(db, user.id, session, "parcelado")
        process_slot_answer(db, user.id, session, "2")
        process_slot_answer(db, user.id, session, "mensal")
        process_slot_answer(db, user.id, session, "1")
        result = process_slot_answer(db, user.id, session, "hoje")

        assert result.question is not None
        assert "vencimento" not in result.question.lower()
        wizard = session["transaction_wizard"]
        assert wizard.get("due_date") == "2026-09-14"
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
async def test_expense_asks_payment_source_before_status():
    from app.config import settings
    from app.models import CreditCard

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"slots_pay_src_{suffix}@test.com",
        password="secret1",
        name="Pay Source",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        account_name = f"Mercado Pago_{suffix}"
        _create_account(db, user.id, account_name)
        finance.create_card(
            db,
            user.id,
            CreateCardInput(
                name=f"Cartão_{suffix}",
                closing_day=9,
                due_day=14,
                settlement_account_name=account_name,
            ),
        )
        session = {}
        tool_call = ToolCall(
            tool="register_expense",
            arguments={"amount": "40", "description": "mercado"},
        )
        result = ensure_transaction_slots(db, user.id, session, tool_call, "gastei 40 no mercado")
        assert result.question is not None
        assert "cartão" in result.question.lower()
        assert "conta" in result.question.lower()
    finally:
        from app.models import CardInvoice

        db.query(CardInvoice).filter(CardInvoice.user_id == user.id).delete(synchronize_session=False)
        db.query(CreditCard).filter(CreditCard.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_income_message_seeds_amount_without_asking_again():
    from app.agent.runner import _seed_register_arguments, _resolve_intent

    message = "Lance uma receita de 594 referente ao auxílio transporte"
    seeded = _seed_register_arguments(message)
    assert seeded.get("amount") == "594"
    assert "auxílio" in seeded.get("description", "").lower() or "transporte" in seeded.get(
        "description", ""
    ).lower()

    tool_call, source = await _resolve_intent(message)
    assert tool_call is not None
    assert tool_call.tool == "register_income"
    assert tool_call.arguments.get("amount") == "594"
    assert source == "rule"

    from app.config import settings

    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"seed_amt_{suffix}@test.com",
        password="secret1",
        name="Seed Amt",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        _create_account(db, user.id, f"Flash_{suffix}")
        session = {}
        result = ensure_transaction_slots(db, user.id, session, tool_call, message)
        wizard = session["transaction_wizard"]
        assert wizard.get("amount") == "594"
        assert result.question is not None
        assert "valor" not in result.question.lower()
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(
            synchronize_session=False
        )
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()
