import uuid
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import create_user
from app.models import Account, Category, Transaction, User
from app.schemas import (
    CreateAccountInput,
    ListTransactionsInput,
    RealizePlannedInput,
    RegisterExpenseInput,
    SummaryInput,
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


@pytest.mark.asyncio
async def test_planned_expense_does_not_affect_balance():
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"planned_{suffix}@test.com",
        password="secret1",
        name="Planned User",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        account = _create_account(db, user.id, f"Conta_{suffix}", opening_balance="1000")
        balance_before = finance.account_balances(db, user.id)[0]["balance_cents"]

        finance.register_expense(
            db,
            user.id,
            RegisterExpenseInput(
                amount="200",
                description="Mercado previsto",
                account_name=account["name"],
                category_name="Alimentação",
                transaction_date=local_today(),
                status="planned",
            ),
        )
        balance_after = finance.account_balances(db, user.id)[0]["balance_cents"]
        assert balance_after == balance_before
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_projected_balance_includes_opening_balance_and_pending_planned():
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"proj_{suffix}@test.com",
        password="secret1",
        name="Proj User",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        today = local_today()
        month_start = today.replace(day=1)
        account = _create_account(
            db,
            user.id,
            f"Conta_{suffix}",
            opening_balance="1000",
            opening_balance_date=month_start - timedelta(days=1),
        )
        finance.register_expense(
            db,
            user.id,
            RegisterExpenseInput(
                amount="200",
                description="Aluguel previsto",
                account_name=account["name"],
                category_name="Moradia",
                transaction_date=today,
                status="planned",
            ),
        )
        summary = finance.get_summary(db, user.id, SummaryInput(ref_date=today, period="month"))
        assert summary["previous_balance_cents"] == 100000
        assert summary["ending_balance_cents"] == 100000
        assert summary["pending_planned_expense_cents"] == 20000
        assert summary["projected_ending_balance_cents"] == 80000
        assert summary["projected_ending_balance"] == "800,00"
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_realized_planned_not_counted_in_pending_projection():
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"proj2_{suffix}@test.com",
        password="secret1",
        name="Proj User 2",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        account = _create_account(db, user.id, f"Conta_{suffix}", opening_balance="500")
        today = local_today()
        planned = finance.register_expense(
            db,
            user.id,
            RegisterExpenseInput(
                amount="100",
                description="Internet",
                account_name=account["name"],
                category_name="Moradia",
                transaction_date=today,
                status="planned",
            ),
        )
        finance.realize_planned(
            db,
            user.id,
            RealizePlannedInput(planned_id=planned["id"], amount="100"),
        )
        summary = finance.get_summary(db, user.id, SummaryInput(ref_date=today, period="month"))
        assert summary["pending_planned_expense_cents"] == 0
        assert summary["projected_ending_balance_cents"] == summary["ending_balance_cents"]
        assert summary["ending_balance_cents"] == 40000
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_realize_planned_creates_linked_actual_and_updates_balance():
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"realize_{suffix}@test.com",
        password="secret1",
        name="Realize User",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        account = _create_account(db, user.id, f"Conta_{suffix}", opening_balance="1000")
        planned = finance.register_expense(
            db,
            user.id,
            RegisterExpenseInput(
                amount="150",
                description="Internet",
                account_name=account["name"],
                category_name="Moradia",
                transaction_date=local_today() + timedelta(days=5),
                status="planned",
            ),
        )
        balance_before = finance.account_balances(db, user.id)[0]["balance_cents"]

        result = finance.realize_planned(
            db,
            user.id,
            RealizePlannedInput(
                planned_id=planned["id"],
                amount="160",
                transaction_date=local_today(),
            ),
        )
        balance_after = finance.account_balances(db, user.id)[0]["balance_cents"]

        assert result["actual"]["source_planned_id"] == planned["id"]
        assert result["actual"]["status"] == "actual"
        assert balance_after == balance_before - 16000
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_cannot_realize_planned_twice():
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"twice_{suffix}@test.com",
        password="secret1",
        name="Twice User",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        account = _create_account(db, user.id, f"Conta_{suffix}")
        planned = finance.register_expense(
            db,
            user.id,
            RegisterExpenseInput(
                amount="50",
                description="Assinatura",
                account_name=account["name"],
                category_name="Lazer",
                status="planned",
            ),
        )
        finance.realize_planned(
            db,
            user.id,
            RealizePlannedInput(planned_id=planned["id"]),
        )
        with pytest.raises(ValueError, match="já foi realizado"):
            finance.realize_planned(
                db,
                user.id,
                RealizePlannedInput(planned_id=planned["id"]),
            )
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_realize_planned_updates_planned_account_when_different():
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"acct_{suffix}@test.com",
        password="secret1",
        name="Account User",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        account_a = _create_account(db, user.id, f"ContaA_{suffix}", opening_balance="1000")
        account_b = _create_account(db, user.id, f"ContaB_{suffix}", opening_balance="500")
        planned = finance.register_expense(
            db,
            user.id,
            RegisterExpenseInput(
                amount="80",
                description="Conta diferente",
                account_name=account_a["name"],
                category_name="Alimentação",
                status="planned",
            ),
        )
        assert planned["account"] == account_a["name"]

        result = finance.realize_planned(
            db,
            user.id,
            RealizePlannedInput(
                planned_id=planned["id"],
                account_name=account_b["name"],
                payment_date=local_today(),
            ),
        )

        assert result["planned"]["account"] == account_b["name"]
        assert result["actual"]["account"] == account_b["name"]
        assert result["actual"]["source_planned_id"] == planned["id"]
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_wants_planned_movement_intent():
    from app.services.intents import wants_planned_movement
    from app.services.tools import try_rule_based_parse

    assert wants_planned_movement("vou gastar 50 no mercado")
    result = try_rule_based_parse("vou gastar 50 no mercado")
    assert result is not None
    assert result.tool == "register_expense"
    assert "status" not in result.arguments


def test_get_summary_includes_planned_totals():
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"summary_{suffix}@test.com",
        password="secret1",
        name="Summary User",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        account = _create_account(db, user.id, f"Conta_{suffix}")
        today = local_today()
        finance.register_expense(
            db,
            user.id,
            RegisterExpenseInput(
                amount="80",
                description="Previsão mercado",
                account_name=account["name"],
                category_name="Alimentação",
                transaction_date=today,
                status="planned",
            ),
        )
        summary = finance.get_summary(db, user.id, SummaryInput(ref_date=today, period="month"))
        assert summary["planned_expense_cents"] == 8000
        assert summary["expense_cents"] == 0
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_list_transactions_filters_by_status():
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"filter_{suffix}@test.com",
        password="secret1",
        name="Filter User",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        account = _create_account(db, user.id, f"Conta_{suffix}", opening_balance="1000")
        today = local_today()

        planned = finance.register_expense(
            db,
            user.id,
            RegisterExpenseInput(
                amount="100",
                description="Previsto filtro",
                account_name=account["name"],
                category_name="Alimentação",
                transaction_date=today,
                status="planned",
            ),
        )
        finance.register_expense(
            db,
            user.id,
            RegisterExpenseInput(
                amount="50",
                description="Realizado filtro",
                account_name=account["name"],
                category_name="Alimentação",
                transaction_date=today,
                status="actual",
            ),
        )

        planned_only = finance.list_transactions(
            db, user.id, ListTransactionsInput(limit=50, status="planned")
        )
        actual_only = finance.list_transactions(
            db, user.id, ListTransactionsInput(limit=50, status="actual")
        )

        assert all(tx["status"] == "planned" for tx in planned_only)
        assert any(tx["id"] == planned["id"] for tx in planned_only)
        assert all(tx["status"] == "actual" for tx in actual_only)
        assert not any(tx["status"] == "planned" for tx in actual_only)
        assert any(tx["description"] == "Realizado filtro" for tx in actual_only)
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()
