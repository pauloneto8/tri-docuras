import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import create_user
from app.models import Account, Budget, Category, Transaction, User
from app.schemas import (
    BudgetCreate,
    BudgetStatusInput,
    CreateAccountInput,
    RealizePlannedInput,
    RegisterExpenseInput,
    SummaryInput,
    TransactionCreate,
)
from app.services import finance
from app.timezone import local_today


def _setup_user(db, user):
    finance.seed_defaults(db, user.id)


def _create_account(db, user_id, name, **kwargs):
    return finance.create_account(
        db,
        user_id,
        CreateAccountInput(name=name, account_type="corrente", **kwargs),
    )


def test_resolve_transaction_dates_planned_has_no_payment():
    comp, due, payment, cash = finance.resolve_transaction_dates(
        "planned",
        competence_date=date(2026, 8, 1),
        due_date=date(2026, 8, 10),
    )
    assert comp == date(2026, 8, 1)
    assert due == date(2026, 8, 10)
    assert payment is None
    assert cash == date(2026, 8, 10)


def test_resolve_transaction_dates_actual_requires_payment():
    comp, due, payment, cash = finance.resolve_transaction_dates(
        "actual",
        payment_date=date(2026, 9, 5),
    )
    assert payment == date(2026, 9, 5)
    assert due == date(2026, 9, 5)
    assert comp == date(2026, 9, 5)
    assert cash == date(2026, 9, 5)


def test_planned_expense_has_null_payment_date():
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"dates_{suffix}@test.com",
        password="secret1",
        name="Dates User",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        account = _create_account(db, user.id, f"Conta_{suffix}")
        today = local_today()
        result = finance.register_expense(
            db,
            user.id,
            RegisterExpenseInput(
                amount="100",
                description="Aluguel previsto",
                account_name=account["name"],
                category_name="Moradia",
                competence_date=today,
                due_date=today + timedelta(days=5),
                status="planned",
            ),
        )
        assert result["payment_date"] is None
        assert result["due_date"] == (today + timedelta(days=5)).isoformat()
        assert result["competence_date"] == today.isoformat()
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete()
        db.commit()
        db.close()


def test_realize_uses_payment_date_for_cash_balance():
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"dates2_{suffix}@test.com",
        password="secret1",
        name="Dates User 2",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        account = _create_account(
            db,
            user.id,
            f"Conta_{suffix}",
            opening_balance="1000",
            opening_balance_date=local_today() - timedelta(days=30),
        )
        comp = date(2026, 8, 1)
        due = date(2026, 8, 10)
        pay = local_today()
        planned = finance.register_expense(
            db,
            user.id,
            RegisterExpenseInput(
                amount="200",
                description="Aluguel",
                account_name=account["name"],
                category_name="Moradia",
                competence_date=comp,
                due_date=due,
                status="planned",
            ),
        )
        balance_before = finance.account_balances(db, user.id)[0]["balance_cents"]
        finance.realize_planned(
            db,
            user.id,
            RealizePlannedInput(
                planned_id=planned["id"],
                payment_date=pay,
                competence_date=comp,
                due_date=due,
            ),
        )
        balance_after = finance.account_balances(db, user.id)[0]["balance_cents"]
        assert balance_before == balance_after + 20000
        summary = finance.get_summary(
            db, user.id, SummaryInput(ref_date=pay, period="month")
        )
        assert summary["expense_cents"] == 20000
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete()
        db.commit()
        db.close()


def test_budget_uses_competence_date_not_payment():
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"budget_{suffix}@test.com",
        password="secret1",
        name="Budget User",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        account = _create_account(db, user.id, f"Conta_{suffix}")
        category = db.scalars(
            __import__("sqlalchemy").select(Category).where(
                Category.user_id == user.id,
                Category.name == "Moradia",
            )
        ).first()
        finance.create_budget(
            db,
            user.id,
            BudgetCreate(category_id=category.id, year=2026, month=8, limit_cents=50000),
        )
        finance.create_transaction(
            db,
            user.id,
            TransactionCreate(
                account_id=account["id"],
                category_id=category.id,
                type="expense",
                amount_cents=15000,
                description="Aluguel agosto",
                competence_date=date(2026, 8, 5),
                due_date=date(2026, 8, 10),
                payment_date=date(2026, 9, 2),
                status="actual",
            ),
        )
        status = finance.get_budget_status(
            db, user.id, BudgetStatusInput(year=2026, month=8)
        )
        moradia = next(s for s in status if s["category"] == "Moradia")
        assert moradia["spent_cents"] == 15000
        # Pagamento em setembro não deve entrar no orçamento de setembro (competência em agosto)
        status_sep = finance.get_budget_status(
            db, user.id, BudgetStatusInput(year=2026, month=9)
        )
        assert all(s["spent_cents"] == 0 for s in status_sep)
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(Budget).filter(Budget.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete()
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_slots_infer_payment_for_actual_ontem():
    from datetime import timedelta

    from app.config import settings
    from app.schemas import ToolCall
    from app.services.transaction_slots import ensure_transaction_slots, process_slot_answer

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"slots_date_{suffix}@test.com",
        password="secret1",
        name="Slots Date",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        _create_account(db, user.id, f"Conta_{suffix}")
        message = "Ontem gastei 40 de passagens"
        tool_call = ToolCall(
            tool="register_expense",
            arguments={"amount": "40", "description": "passagens"},
        )
        session = {}
        result = ensure_transaction_slots(db, user.id, session, tool_call, message)
        assert result.question is not None
        process_slot_answer(db, user.id, session, "realizado")
        wizard = session["transaction_wizard"]
        yesterday = (local_today() - timedelta(days=1)).isoformat()
        assert wizard.get("payment_date") == yesterday or wizard.get("transaction_date") == yesterday
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete()
        db.commit()
        db.close()
