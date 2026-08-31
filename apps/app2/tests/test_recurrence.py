import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.agent.runner import process_message
from app.auth import create_user
from app.models import Account, Category, RecurringRule, Transaction, User
from app.schemas import (
    CreateAccountInput,
    RegisterExpenseInput,
)
from app.services import finance
from app.services.recurrence import (
    anchor_from_date,
    create_recurring_rule,
    deactivate_recurring_rule,
    ensure_recurring_horizon,
    horizon_end,
    iter_occurrences,
    next_occurrence,
)
from app.timezone import local_today


def _setup_user(db, user):
    finance.seed_defaults(db, user.id)


def _create_account(db, user_id, name, **kwargs):
    return finance.create_account(
        db,
        user_id,
        CreateAccountInput(name=name, account_type="corrente", **kwargs),
    )


def test_monthly_next_occurrence_jan_31_to_feb():
    from app.config import settings

    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"rec_{suffix}@test.com",
        password="secret1",
        name="Rec User",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        account = _create_account(db, user.id, f"Conta_{suffix}")
        cat = db.scalar(select(Category).where(Category.user_id == user.id, Category.type == "expense"))
        start = date(2026, 1, 31)
        rule = create_recurring_rule(
            db,
            user.id,
            account_id=account["id"],
            category_id=cat.id,
            tx_type="expense",
            amount_cents=10000,
            description="Aluguel",
            frequency="monthly",
            start_date=start,
        )
        db.commit()
        nxt = next_occurrence(rule, start)
        assert nxt == date(2026, 2, 28)
        nxt2 = next_occurrence(rule, nxt)
        assert nxt2 == date(2026, 3, 31)
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(RecurringRule).filter(RecurringRule.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_horizon_end_respects_end_date():
    today = date(2026, 8, 31)
    end = date(2026, 9, 15)
    assert horizon_end(today, end) == end
    assert horizon_end(today, None) == date(2026, 11, 30)


def test_ensure_horizon_does_not_duplicate():
    from app.config import settings

    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"rec2_{suffix}@test.com",
        password="secret1",
        name="Rec User 2",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        account = _create_account(db, user.id, f"Conta_{suffix}")
        cat = db.scalar(select(Category).where(Category.user_id == user.id, Category.type == "expense"))
        start = local_today().replace(day=1)
        rule = create_recurring_rule(
            db,
            user.id,
            account_id=account["id"],
            category_id=cat.id,
            tx_type="expense",
            amount_cents=5000,
            description="Internet",
            frequency="monthly",
            start_date=start,
        )
        db.commit()
        created1 = ensure_recurring_horizon(db, user.id, rule_id=rule.id, today=start)
        created2 = ensure_recurring_horizon(db, user.id, rule_id=rule.id, today=start)
        assert created1 > 0
        assert created2 == 0
        count = db.scalar(
            select(func.count()).select_from(Transaction).where(
                Transaction.recurrence_id == rule.id
            )
        )
        assert count == created1
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(RecurringRule).filter(RecurringRule.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_register_recurring_creates_rule_and_planned_series():
    from app.config import settings

    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"rec3_{suffix}@test.com",
        password="secret1",
        name="Rec User 3",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        account = _create_account(db, user.id, f"Conta_{suffix}")
        start = local_today().replace(day=5)
        result = finance.register_expense(
            db,
            user.id,
            RegisterExpenseInput(
                amount="120",
                description="Assinatura",
                account_name=account["name"],
                category_name="Lazer",
                competence_date=start,
                due_date=start,
                status="planned",
                frequency="monthly",
            ),
        )
        assert result["recurrence_id"] is not None
        assert result["frequency"] == "monthly"
        txs = db.scalars(
            select(Transaction).where(Transaction.recurrence_id == result["recurrence_id"])
        ).all()
        assert len(txs) >= 2
        assert all(tx.status == "planned" for tx in txs[1:])
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(RecurringRule).filter(RecurringRule.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_deactivate_removes_pending_not_realized():
    from app.config import settings
    from app.schemas import RealizePlannedInput

    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"rec4_{suffix}@test.com",
        password="secret1",
        name="Rec User 4",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        account = _create_account(db, user.id, f"Conta_{suffix}", opening_balance="1000")
        start = local_today()
        first = finance.register_expense(
            db,
            user.id,
            RegisterExpenseInput(
                amount="50",
                description="Gym",
                account_name=account["name"],
                category_name="Lazer",
                competence_date=start,
                due_date=start,
                status="planned",
                frequency="monthly",
            ),
        )
        rule_id = first["recurrence_id"]
        pending = db.scalars(
            select(Transaction).where(
                Transaction.recurrence_id == rule_id,
                Transaction.status == "planned",
            )
        ).all()
        assert len(pending) >= 2
        to_realize = pending[0]
        finance.realize_planned(
            db,
            user.id,
            RealizePlannedInput(planned_id=to_realize.id, payment_date=start),
        )
        before = db.scalar(
            select(func.count()).select_from(Transaction).where(
                Transaction.recurrence_id == rule_id
            )
        )
        deactivate_recurring_rule(db, user.id, rule_id)
        after = db.scalar(
            select(func.count()).select_from(Transaction).where(
                Transaction.recurrence_id == rule_id
            )
        )
        assert after < before
        assert after >= 1
        rule = db.get(RecurringRule, rule_id)
        assert rule.is_active is False
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(RecurringRule).filter(RecurringRule.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_wizard_recurring_does_not_trigger_multi():
    from app.config import settings

    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"recwiz_{suffix}@test.com",
        password="secret1",
        name="Wiz User",
        is_active=True,
    )
    session: dict = {}
    try:
        finance.seed_defaults(db, user.id)
        finance.create_account(
            db,
            user.id,
            CreateAccountInput(name=f"Carteira_{suffix}", account_type="carteira"),
        )
        from app.services.transaction_wizard import begin_login_prompt, try_process_transaction_wizard

        begin_login_prompt(session)
        try_process_transaction_wizard(session, "despesa", db=db, user_id=user.id)
        try_process_transaction_wizard(session, "previsto", db=db, user_id=user.id)
        try_process_transaction_wizard(session, "agosto", db=db, user_id=user.id)
        try_process_transaction_wizard(session, "10/08/2026", db=db, user_id=user.id)

        with patch("app.agent.runner.call_intent_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = (None, "groq")
            result = await process_message(db, user.id, "Sim", session=session)

        assert "frequência" in result.message.lower() or "fixo" in result.message.lower()
        mock_llm.assert_not_called()
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(RecurringRule).filter(RecurringRule.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()
