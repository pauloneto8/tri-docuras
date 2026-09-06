"""Regressões a partir de conversas reais do chat."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import create_user
from app.models import Account, Category, CreditCard, Transaction, User
from app.schemas import CreateAccountInput, CreateCardInput, ToolCall
from app.services import finance
from app.services.multi_movements import parse_multi_movements
from app.services.text_correction import correct_movement_description, sanitize_movement_description
from app.services.tools import extract_description, parse_amount
from app.services.transaction_slots import (
    ensure_transaction_slots,
    wants_card_payment,
)


def test_parse_amount_ignores_installment_count():
    assert parse_amount("comprei uma blusa em 10 vezes") is None
    assert parse_amount("Lance no cartão uma compra em 3 vezes") is None
    assert parse_amount("Lance na fatura 9,67 em 10 vezes") == "9.67"
    assert parse_amount("gastei 45,90 no mercado") == "45.90"
    assert parse_amount("12x de 99,90") == "99.90"


def test_fatura_phrase_is_not_multi_movement():
    msg = (
        "Lance na fatura do mercado pago 9,67 em 10 vezes, "
        "referente a compra na Shopee"
    )
    assert parse_multi_movements(msg) is None


def test_wants_card_payment_from_fatura():
    assert wants_card_payment("Lance na fatura do mercado pago 9,67 em 10 vezes")
    assert wants_card_payment("gastei no cartão mercado pago")
    assert not wants_card_payment("pagar a fatura do mercado pago")


def test_description_strips_valor_de_and_vezes():
    assert "valor" not in sanitize_movement_description("Carne de Boi o valor de").lower()
    assert correct_movement_description("Carne de Boi o valor de") == "Carne de Boi"
    desc = extract_description(
        "Eu comprei uma blusa em 10 vezes no cartão do mercado pago",
        None,
    )
    assert "blusa" in desc.lower()
    assert "vezes" not in desc.lower()
    desc2 = extract_description(
        "Lance no cartão uma compra em 3 vezes, referente ao presente do dia dos pais",
        None,
    )
    assert "presente" in desc2.lower()
    assert "vezes" not in desc2.lower()


def _setup_user(db, user):
    finance.seed_defaults(db, user.id)


@pytest.mark.asyncio
async def test_installment_without_amount_asks_value_not_uses_count():
    from app.config import settings

    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"reg_amt_{suffix}@test.com",
        password="secret1",
        name="Reg Amt",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        account = f"MP_{suffix}"
        finance.create_account(
            db, user.id, CreateAccountInput(name=account, account_type="corrente")
        )
        finance.create_card(
            db,
            user.id,
            CreateCardInput(
                name=f"Cartão_{suffix}",
                closing_day=9,
                due_day=14,
                settlement_account_name=account,
            ),
        )
        message = (
            f"Lance no cartão {suffix} uma compra em 3 vezes, "
            "referente ao presente do dia dos pais"
        )
        # Mensagem sem nome exato do cartão — usa "no cartão"
        message = (
            "Lance no cartão uma compra em 3 vezes, "
            "referente ao presente do dia dos pais"
        )
        tool_call = ToolCall(tool="register_expense", arguments={})
        session = {}
        result = ensure_transaction_slots(db, user.id, session, tool_call, message)
        wizard = session["transaction_wizard"]
        assert wizard["payment_mode"] == "installment"
        assert wizard["installment_count"] == 3
        assert wizard["installment_interval"] == "monthly"
        assert wizard["amount"] is None
        assert wizard["payment_source"] == "card"
        assert wizard["card_name"]  # único cartão auto
        assert "presente" in (wizard.get("description") or "").lower()
        assert result.question is not None
        q = result.question.lower()
        # Deve perguntar valor (ou competência/parcela), nunca tratar 3 como R$ 3
        assert "3,00" not in result.question
        assert "r$ 3" not in q
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(
            synchronize_session=False
        )
        from app.models import CardInvoice

        db.query(CardInvoice).filter(CardInvoice.user_id == user.id).delete(
            synchronize_session=False
        )
        db.query(CreditCard).filter(CreditCard.user_id == user.id).delete(
            synchronize_session=False
        )
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_fatura_installment_keeps_amount_and_card():
    from app.config import settings

    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"reg_fat_{suffix}@test.com",
        password="secret1",
        name="Reg Fat",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        account = f"Mercado Pago_{suffix}"
        card = f"Mercado Pago_{suffix}"
        finance.create_account(
            db, user.id, CreateAccountInput(name=account, account_type="corrente")
        )
        finance.create_card(
            db,
            user.id,
            CreateCardInput(
                name=card,
                closing_day=9,
                due_day=14,
                settlement_account_name=account,
            ),
        )
        message = (
            f"Lance na fatura do mercado pago 9,67 em 10 vezes, "
            "referente a compra na Shopee"
        )
        tool_call = ToolCall(
            tool="register_expense",
            arguments={"amount": "9.67", "description": "compra na Shopee"},
        )
        session = {}
        result = ensure_transaction_slots(db, user.id, session, tool_call, message)
        wizard = session["transaction_wizard"]
        assert wizard["payment_source"] == "card"
        assert wizard["card_name"] == card
        assert wizard["payment_mode"] == "installment"
        assert wizard["installment_count"] == 10
        assert wizard["installment_interval"] == "monthly"
        assert wizard["amount"] in {"9.67", "9,67"}
        assert result.question is not None
        # Não perguntar cartão vs conta
        q = result.question.lower()
        assert not ("cartão de crédito" in q and "conta bancária" in q)
    finally:
        from app.models import CardInvoice

        db.query(Transaction).filter(Transaction.user_id == user.id).delete(
            synchronize_session=False
        )
        db.query(CardInvoice).filter(CardInvoice.user_id == user.id).delete(
            synchronize_session=False
        )
        db.query(CreditCard).filter(CreditCard.user_id == user.id).delete(
            synchronize_session=False
        )
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()
