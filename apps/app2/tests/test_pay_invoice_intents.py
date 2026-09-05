import uuid
from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.auth import create_user
from app.models import Account, CardInvoice, Category, CreditCard, InstallmentPlan, Transaction, User
from app.schemas import CreateAccountInput, CreateCardInput, RegisterExpenseInput, ToolCall
from app.services import finance
from app.services.credit_cards import (
    parse_invoice_period_hint,
    pay_invoice,
    preview_payable_invoice,
)
from app.services.intents import detect_pay_invoice, wants_pay_invoice
from app.services.pay_invoice_slots import ensure_pay_invoice_slots


def test_wants_pay_invoice_includes_baixar():
    assert wants_pay_invoice("baixar a fatura do cartão")
    assert wants_pay_invoice("liquidar fatura de setembro")
    assert wants_pay_invoice("pagar fatura do mercado pago")


def test_detect_pay_invoice_ignores_month_as_card():
    data = detect_pay_invoice("Faça o pagamento da minha fatura de setembro")
    assert "account_name" not in data
    assert "from_account_name" not in data
    assert data.get("due_month") == 9


def test_detect_pay_invoice_extracts_card_and_account():
    data = detect_pay_invoice(
        "pagar fatura do cartão Mercado Pago com conta Carteira"
    )
    assert "mercado pago" in data.get("account_name", "").lower()
    assert "carteira" in data.get("from_account_name", "").lower()


def test_parse_invoice_period_hint_numeric():
    assert parse_invoice_period_hint("fatura 09/2026", ref_date=date(2026, 9, 4)) == (9, 2026)


def test_pay_invoice_wizard_resolves_september_invoice():
    from app.config import settings

    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"paywiz_{suffix}@test.com",
        password="secret1",
        name="Pay Wizard",
        is_active=True,
    )
    try:
        finance.seed_defaults(db, user.id)
        debit = finance.create_account(
            db,
            user.id,
            CreateAccountInput(
                name=f"Carteira_{suffix}",
                account_type="carteira",
                opening_balance="500",
                opening_balance_date=date(2026, 1, 1),
            ),
        )
        card = finance.create_card(
            db,
            user.id,
            CreateCardInput(
                name=f"Mercado Pago_{suffix}",
                closing_day=9,
                due_day=14,
                settlement_account_name=debit["name"],
            ),
        )
        cat = db.scalar(
            select(Category).where(Category.user_id == user.id, Category.type == "expense")
        )
        finance.register_expense(
            db,
            user.id,
            RegisterExpenseInput(
                amount="30",
                description="Compra teste",
                card_name=card["name"],
                category_name=cat.name,
                competence_date=date(2026, 9, 3),
            ),
        )
        message = "Faça o pagamento da minha fatura de setembro"
        session = {}
        tool_call = ToolCall(tool="pay_invoice", arguments=detect_pay_invoice(message))
        result = ensure_pay_invoice_slots(db, user.id, session, tool_call, message)
        wizard = session["pay_invoice_wizard"]
        assert wizard.get("account_name") == card["name"]
        assert wizard.get("invoice_total") is not None
        assert wizard.get("from_account_name") == debit["name"]
        assert "30,00" in wizard.get("invoice_total", "")
        assert result.tool_call is not None or result.question is not None

        preview = preview_payable_invoice(
            db,
            user.id,
            card_name=card["name"],
            due_month=9,
            due_year=2026,
        )
        assert preview is not None
        pay_invoice(
            db,
            user.id,
            invoice_id=preview["id"],
            from_account_name=debit["name"],
            payment_date=date(2026, 9, 4),
        )
        inv = db.get(CardInvoice, preview["id"])
        assert inv.status == "paid"
        txs = db.scalars(
            select(Transaction).where(
                Transaction.user_id == user.id,
                Transaction.invoice_id == preview["id"],
            )
        ).all()
        assert txs
        assert all(tx.status == "actual" for tx in txs)
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(
            synchronize_session=False
        )
        db.query(CardInvoice).filter(CardInvoice.user_id == user.id).delete(
            synchronize_session=False
        )
        db.query(CreditCard).filter(CreditCard.user_id == user.id).delete(
            synchronize_session=False
        )
        db.query(InstallmentPlan).filter(InstallmentPlan.user_id == user.id).delete(
            synchronize_session=False
        )
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()
