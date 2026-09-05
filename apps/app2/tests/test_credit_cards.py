import uuid
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.agent.runner import process_message
from app.auth import create_user
from app.models import CardInvoice, Category, CreditCard, Transaction, User
from app.schemas import CreateAccountInput, CreateCardInput, ListTransactionsInput, RegisterExpenseInput, SummaryInput
from app.services import finance
from app.services.credit_cards import (
    cycle_for_purchase,
    cycle_end_for_purchase,
    pay_invoice,
)


def _setup_user(db, user):
    finance.seed_defaults(db, user.id)


def _create_card(db, user_id, name, settlement_account_name, closing=10, due=17, limit="5000"):
    return finance.create_card(
        db,
        user_id,
        CreateCardInput(
            name=name,
            institution="Nubank",
            closing_day=closing,
            due_day=due,
            credit_limit=limit,
            settlement_account_name=settlement_account_name,
        ),
    )


def _create_debit(db, user_id, name, balance="10000"):
    return finance.create_account(
        db,
        user_id,
        CreateAccountInput(
            name=name,
            account_type="corrente",
            opening_balance=balance,
            opening_balance_date=date(2026, 1, 1),
        ),
    )


def _cleanup(db, user_id):
    db.query(Transaction).filter(Transaction.user_id == user_id).delete(
        synchronize_session=False
    )
    from app.models import Account, InstallmentPlan

    db.query(InstallmentPlan).filter(InstallmentPlan.user_id == user_id).delete(
        synchronize_session=False
    )
    db.query(CardInvoice).filter(CardInvoice.user_id == user_id).delete(
        synchronize_session=False
    )
    db.query(CreditCard).filter(CreditCard.user_id == user_id).delete(
        synchronize_session=False
    )

    db.query(Account).filter(Account.user_id == user_id).delete(synchronize_session=False)
    db.query(Category).filter(Category.user_id == user_id).delete(synchronize_session=False)
    db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
    db.commit()


def test_purchase_after_closing_goes_to_next_invoice():
    start, end, due = cycle_for_purchase(10, 17, date(2026, 8, 11))
    assert end == date(2026, 9, 10)
    assert due == date(2026, 9, 17)


def test_purchase_before_closing_same_cycle():
    start, end, due = cycle_for_purchase(10, 17, date(2026, 8, 5))
    assert end == date(2026, 8, 10)
    assert due == date(2026, 8, 17)


def test_closing_day_31_in_february():
    end = cycle_end_for_purchase(date(2026, 1, 31), 31)
    assert end == date(2026, 1, 31)
    end_feb = cycle_end_for_purchase(date(2026, 2, 15), 31)
    assert end_feb == date(2026, 2, 28)


def test_card_expense_assigned_to_invoice():
    from app.config import settings

    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"card_{suffix}@test.com",
        password="secret1",
        name="Card User",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        debit = _create_debit(db, user.id, f"Corrente_{suffix}")
        card = _create_card(db, user.id, f"Nubank_{suffix}", debit["name"])
        cat = db.scalar(
            select(Category).where(Category.user_id == user.id, Category.type == "expense")
        )
        purchase = date(2026, 8, 11)
        finance.register_expense(
            db,
            user.id,
            RegisterExpenseInput(
                amount="150",
                description="Mercado",
                card_name=card["name"],
                category_name=cat.name,
                competence_date=purchase,
                due_date=purchase,
                payment_date=purchase,
                status="actual",
            ),
        )
        txs = db.scalars(
            select(Transaction).where(
                Transaction.user_id == user.id,
                Transaction.card_id == card["id"],
            )
        ).all()
        assert len(txs) == 1
        assert txs[0].status == "planned"
        assert txs[0].payment_date is None
        assert txs[0].invoice_id is not None
        assert txs[0].card_id == card["id"]
        inv = db.get(CardInvoice, txs[0].invoice_id)
        assert inv.due_date == date(2026, 9, 17)
    finally:
        _cleanup(db, user.id)
        db.close()


def test_card_expense_with_linked_account():
    from app.config import settings

    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"cardacc_{suffix}@test.com",
        password="secret1",
        name="Card Account User",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        debit = _create_debit(db, user.id, f"Corrente_{suffix}")
        card = finance.create_card(
            db,
            user.id,
            CreateCardInput(
                name=f"Nubank_{suffix}",
                closing_day=10,
                due_day=17,
                settlement_account_name=debit["name"],
            ),
        )
        cat = db.scalar(
            select(Category).where(Category.user_id == user.id, Category.type == "expense")
        )
        purchase = date(2026, 8, 5)
        finance.register_expense(
            db,
            user.id,
            RegisterExpenseInput(
                amount="80",
                description="Padaria",
                card_name=card["name"],
                account_name=debit["name"],
                category_name=cat.name,
                competence_date=purchase,
                due_date=purchase,
                payment_date=purchase,
                status="actual",
            ),
        )
        tx = db.scalar(select(Transaction).where(Transaction.user_id == user.id))
        assert tx.card_id == card["id"]
        assert tx.account_id == debit["id"]
        assert tx.invoice_id is not None
    finally:
        _cleanup(db, user.id)
        db.close()


def test_pay_invoice_marks_paid_and_debits_account():
    from app.config import settings

    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"card2_{suffix}@test.com",
        password="secret1",
        name="Card User 2",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        debit = _create_debit(db, user.id, f"Corrente_{suffix}")
        card = _create_card(db, user.id, f"Cartao_{suffix}", debit["name"])
        cat = db.scalar(
            select(Category).where(Category.user_id == user.id, Category.type == "expense")
        )
        purchase = date(2026, 8, 5)
        finance.register_expense(
            db,
            user.id,
            RegisterExpenseInput(
                amount="200",
                description="Farmácia",
                card_name=card["name"],
                category_name=cat.name,
                competence_date=purchase,
                due_date=purchase,
                payment_date=purchase,
                status="actual",
            ),
        )
        inv = db.scalar(
            select(CardInvoice).where(
                CardInvoice.card_id == card["id"],
                CardInvoice.due_date == date(2026, 8, 17),
            )
        )
        from app.services.credit_cards import close_due_invoices

        close_due_invoices(db, user_id=user.id, today=date(2026, 8, 20))
        db.refresh(inv)
        assert inv.status == "closed"

        expense_before = db.scalar(
            select(func.coalesce(func.sum(Transaction.amount_cents), 0)).where(
                Transaction.user_id == user.id,
                Transaction.type == "expense",
                Transaction.card_id.is_(None),
            )
        )
        pay_invoice(
            db,
            user.id,
            invoice_id=inv.id,
            from_account_name=debit["name"],
            payment_date=date(2026, 8, 17),
        )
        db.refresh(inv)
        assert inv.status == "paid"
        expense_after = db.scalar(
            select(func.coalesce(func.sum(Transaction.amount_cents), 0)).where(
                Transaction.user_id == user.id,
                Transaction.type == "expense",
                Transaction.card_id.is_(None),
            )
        )
        assert expense_after == expense_before + 20000
    finally:
        _cleanup(db, user.id)
        db.close()


def test_summary_includes_card_invoices():
    from app.config import settings

    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"carddash_{suffix}@test.com",
        password="secret1",
        name="Card Dash",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        debit = _create_debit(db, user.id, f"Corrente_{suffix}")
        card = _create_card(db, user.id, f"Nubank_{suffix}", debit["name"])
        cat = db.scalar(
            select(Category).where(Category.user_id == user.id, Category.type == "expense")
        )
        purchase = date(2026, 8, 11)
        finance.register_expense(
            db,
            user.id,
            RegisterExpenseInput(
                amount="150",
                description="Mercado",
                card_name=card["name"],
                category_name=cat.name,
                competence_date=purchase,
                due_date=purchase,
                payment_date=purchase,
                status="actual",
            ),
        )

        empty = finance.get_summary(
            db, user.id, SummaryInput(period="month", ref_date=date(2026, 8, 15))
        )
        assert empty["ending_balance_cents"] == 1_000_000
        invoices_aug = empty["card_invoices"]
        assert invoices_aug["unpaid_total_cents"] == 15000
        assert invoices_aug["unpaid_count"] == 1
        assert invoices_aug["due_in_period_cents"] == 0
        assert invoices_aug["cards"][0]["name"] == card["name"]
        assert invoices_aug["cards"][0]["current_invoice_total_cents"] == 15000
        assert invoices_aug["cards"][0]["current_invoice_due"] == "2026-09-17"
        assert invoices_aug["cards"][0]["due_in_period"] is False
        assert invoices_aug["cards"][0]["available_limit_cents"] == 500000 - 15000

        sept = finance.get_summary(
            db, user.id, SummaryInput(period="month", ref_date=date(2026, 9, 2))
        )
        invoices_sept = sept["card_invoices"]
        assert invoices_sept["unpaid_total_cents"] == 15000
        assert invoices_sept["due_in_period_cents"] == 15000
        assert invoices_sept["due_in_period_count"] == 1
        assert invoices_sept["cards"][0]["due_in_period"] is True
        assert invoices_sept["cards"][0]["current_invoice_status_label"] in {"Aberta", "Fechada"}

        from app.services.tools import format_tool_result

        text = format_tool_result("get_summary", sept)
        assert "Faturas em aberto: R$ 150,00" in text
        assert card["name"] in text
        assert "17/09/2026" in text
    finally:
        _cleanup(db, user.id)
        db.close()


def test_summary_without_cards_has_empty_invoices():
    from app.config import settings

    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"nocard_{suffix}@test.com",
        password="secret1",
        name="No Card",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        _create_debit(db, user.id, f"Corrente_{suffix}")
        summary = finance.get_summary(db, user.id, SummaryInput())
        invoices = summary["card_invoices"]
        assert invoices["cards"] == []
        assert invoices["unpaid_total_cents"] == 0
        assert invoices["unpaid_count"] == 0
        from app.services.tools import format_tool_result

        text = format_tool_result("get_summary", summary)
        assert "Faturas em aberto" not in text
    finally:
        _cleanup(db, user.id)
        db.close()


def test_pay_invoice_settles_planned_card_transactions():
    from app.config import settings
    from app.services.installments import create_installment_plan

    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"cardsettle_{suffix}@test.com",
        password="secret1",
        name="Card Settle",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        debit = _create_debit(db, user.id, f"Corrente_{suffix}")
        card_data = _create_card(db, user.id, f"MP_{suffix}", debit["name"])
        card = db.get(CreditCard, card_data["id"])
        cat = db.scalar(
            select(Category).where(Category.user_id == user.id, Category.type == "expense")
        )
        purchase = date(2026, 9, 3)
        plan, txs = create_installment_plan(
            db,
            user.id,
            account_id=debit["id"],
            card_id=card.id,
            category_id=cat.id,
            tx_type="expense",
            total_cents=4500,
            installment_count=3,
            interval="monthly",
            start_date=purchase,
            description="Presente",
            first_status="planned",
            competence_date=purchase,
            due_date=date(2026, 9, 14),
            amount_basis="installment",
        )
        db.commit()
        first_tx = txs[0]
        assert first_tx.status == "planned"
        assert first_tx.invoice_id is not None
        invoice_id = first_tx.invoice_id

        pay_invoice(
            db,
            user.id,
            invoice_id=invoice_id,
            from_account_name=debit["name"],
            payment_date=date(2026, 9, 4),
        )
        db.refresh(first_tx)
        assert first_tx.status == "actual"
        assert first_tx.payment_date == date(2026, 9, 4)

        pending = finance.list_transactions(
            db, user.id, ListTransactionsInput(limit=20, status="planned")
        )
        pending_ids = {tx["id"] for tx in pending if not tx["is_realized"]}
        assert first_tx.id not in pending_ids
        assert txs[1].id in pending_ids
    finally:
        _cleanup(db, user.id)
        db.close()

def test_mercado_pago_cycle_sept_vs_oct():
    """Fechamento 9 / vencimento 14: 05/09 → fatura 14/09; 14/09 → fatura 14/10."""
    _, end_early, due_early = cycle_for_purchase(9, 14, date(2026, 9, 5))
    assert end_early == date(2026, 9, 9)
    assert due_early == date(2026, 9, 14)

    _, end_late, due_late = cycle_for_purchase(9, 14, date(2026, 9, 14))
    assert end_late == date(2026, 10, 9)
    assert due_late == date(2026, 10, 14)


def test_card_expense_uses_due_date_as_invoice_anchor():
    """Competência após fechamento não deve sozinha escolher a fatura se due_date for do ciclo certo."""
    from app.config import settings

    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"card_due_{suffix}@test.com",
        password="secret1",
        name="Card Due",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        debit = _create_debit(db, user.id, f"Corrente_{suffix}")
        card = _create_card(
            db, user.id, f"MP_{suffix}", debit["name"], closing=9, due=14
        )
        cat = db.scalar(
            select(Category).where(Category.user_id == user.id, Category.type == "expense")
        )
        result = finance.register_expense(
            db,
            user.id,
            RegisterExpenseInput(
                amount="17.54",
                description="Camisa",
                card_name=card["name"],
                category_name=cat.name,
                competence_date=date(2026, 9, 14),
                due_date=date(2026, 9, 14),
                status="planned",
            ),
        )
        assert result["invoice_label"] == "Fatura · 14/09"
        assert result["due_date"] == "2026-09-14"
    finally:
        _cleanup(db, user.id)
        db.close()


def test_update_moves_card_expense_to_september_invoice():
    from app.config import settings
    from app.schemas import UpdateTransactionInput
    from app.services.credit_cards import invoice_totals
    from app.services.finance import update_transaction

    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"card_move_{suffix}@test.com",
        password="secret1",
        name="Card Move",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        debit = _create_debit(db, user.id, f"Corrente_{suffix}")
        card = _create_card(
            db, user.id, f"MP_{suffix}", debit["name"], closing=9, due=14
        )
        cat = db.scalar(
            select(Category).where(Category.user_id == user.id, Category.type == "expense")
        )
        created = finance.register_expense(
            db,
            user.id,
            RegisterExpenseInput(
                amount="17.54",
                description="Camisa",
                card_name=card["name"],
                category_name=cat.name,
                competence_date=date(2026, 9, 14),
                due_date=date(2026, 10, 14),
                status="planned",
            ),
        )
        assert created["invoice_label"] == "Fatura · 14/10"
        oct_id = created["invoice_id"]

        updated = update_transaction(
            db,
            user.id,
            UpdateTransactionInput(
                transaction_id=created["id"],
                invoice_due_month=9,
                invoice_due_year=2026,
            ),
        )
        assert updated["invoice_label"] == "Fatura · 14/09"
        assert updated["due_date"] == "2026-09-14"
        assert updated.get("invoice_moved") is True

        oct_inv = db.get(CardInvoice, oct_id)
        sept_inv = db.get(CardInvoice, updated["invoice_id"])
        assert invoice_totals(db, oct_inv) == 0
        assert invoice_totals(db, sept_inv) == 1754
    finally:
        _cleanup(db, user.id)
        db.close()


def test_card_installment_before_closing_goes_to_september_invoice():
    """Competência 01/09 + due wizard 14/09 (fechamento 9) → 1ª parcela na fatura 14/09."""
    from app.config import settings

    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"card_inst_sept_{suffix}@test.com",
        password="secret1",
        name="Card Inst Sept",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        debit = _create_debit(db, user.id, f"Corrente_{suffix}")
        card = _create_card(
            db, user.id, f"MP_{suffix}", debit["name"], closing=9, due=14
        )
        cat = db.scalar(
            select(Category).where(Category.user_id == user.id, Category.type == "expense")
        )
        result = finance.register_expense(
            db,
            user.id,
            RegisterExpenseInput(
                amount="32.24",
                description="Farmácia do Trabalhador",
                card_name=card["name"],
                category_name=cat.name,
                competence_date=date(2026, 9, 1),
                # Wizard envia o vencimento da fatura — não pode virar âncora do ciclo.
                due_date=date(2026, 9, 14),
                status="planned",
                installment_count=5,
                installment_interval="monthly",
                installment_start_index=3,
                installment_amount_basis="installment",
            ),
        )
        assert result["installment_index"] == 3
        assert result["due_date"] == "2026-09-14"
        assert result["invoice_label"] == "Fatura · 14/09"
        assert result["competence_date"] == "2026-09-01"

        siblings = db.scalars(
            select(Transaction)
            .where(
                Transaction.user_id == user.id,
                Transaction.installment_plan_id == result["installment_plan_id"],
            )
            .order_by(Transaction.installment_index.asc())
        ).all()
        assert [t.installment_index for t in siblings] == [3, 4, 5]
        assert siblings[0].due_date == date(2026, 9, 14)
        assert siblings[1].due_date == date(2026, 10, 14)
        assert siblings[1].competence_date == date(2026, 10, 1)
        assert siblings[2].due_date == date(2026, 11, 14)
        assert siblings[2].competence_date == date(2026, 11, 1)
    finally:
        _cleanup(db, user.id)
        db.close()
