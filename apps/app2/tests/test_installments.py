import uuid
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.agent.runner import process_message
from app.auth import create_user
from app.models import Account, Category, InstallmentPlan, Transaction, User
from app.schemas import CreateAccountInput, RealizePlannedInput, RegisterExpenseInput
from app.services import finance
from app.services.installments import (
    cancel_installment_plan,
    create_installment_plan,
    due_date_for_index,
    parse_installment_count,
    parse_installment_start_index,
    repeat_cents,
    split_cents,
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


def _cleanup_user(db, user_id):
    db.query(Transaction).filter(Transaction.user_id == user_id).delete(
        synchronize_session=False
    )
    db.query(InstallmentPlan).filter(InstallmentPlan.user_id == user_id).delete(
        synchronize_session=False
    )
    db.query(Account).filter(Account.user_id == user_id).delete(synchronize_session=False)
    db.query(Category).filter(Category.user_id == user_id).delete(synchronize_session=False)
    db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
    db.commit()


def test_split_cents_remainder_on_last():
    assert split_cents(10001, 3) == [3333, 3333, 3335]
    assert sum(split_cents(10001, 3)) == 10001


def test_repeat_cents():
    assert repeat_cents(10000, 12) == [10000] * 12


def test_create_installment_plan_amount_basis_installment():
    from app.config import settings

    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"inst_basis_{suffix}@test.com",
        password="secret1",
        name="Inst Basis",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        account = _create_account(db, user.id, f"Conta_{suffix}")
        start = date(2026, 8, 10)
        plan, txs = create_installment_plan(
            db,
            user.id,
            account_id=account["id"],
            category_id=None,
            tx_type="expense",
            total_cents=10000,
            installment_count=12,
            interval="monthly",
            start_date=start,
            description="Notebook",
            amount_basis="installment",
        )
        assert plan.total_cents == 120000
        assert len(txs) == 12
        assert all(tx.amount_cents == 10000 for tx in txs)
    finally:
        _cleanup_user(db, user.id)
        db.close()


def test_create_installment_plan_amount_basis_total():
    from app.config import settings

    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"inst_total_{suffix}@test.com",
        password="secret1",
        name="Inst Total",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        account = _create_account(db, user.id, f"Conta_{suffix}")
        start = date(2026, 8, 10)
        plan, txs = create_installment_plan(
            db,
            user.id,
            account_id=account["id"],
            category_id=None,
            tx_type="expense",
            total_cents=10001,
            installment_count=3,
            interval="monthly",
            start_date=start,
            description="Curso",
            amount_basis="total",
        )
        assert plan.total_cents == 10001
        assert [tx.amount_cents for tx in txs] == [3333, 3333, 3335]
    finally:
        _cleanup_user(db, user.id)
        db.close()


def test_create_user_transaction_installment_basis_installment():
    from app.config import settings
    from app.schemas import TransactionCreate

    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"inst_form_{suffix}@test.com",
        password="secret1",
        name="Inst Form",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        account = _create_account(db, user.id, f"Conta_{suffix}")
        category = db.scalars(
            select(Category).where(
                Category.user_id == user.id,
                Category.type == "expense",
            )
        ).first()
        data = TransactionCreate(
            account_id=account["id"],
            category_id=category.id,
            type="expense",
            amount_cents=120000,
            description="Notebook",
            competence_date=date(2026, 8, 10),
            due_date=date(2026, 8, 10),
            status="planned",
        )
        result = finance.create_user_transaction(
            db,
            user.id,
            data,
            installment_count=12,
            installment_interval="monthly",
            installment_amount_basis="installment",
        )
        txs = db.scalars(
            select(Transaction).where(
                Transaction.installment_plan_id == result["installment_plan_id"]
            )
        ).all()
        assert len(txs) == 12
        assert all(tx.amount_cents == 120000 for tx in txs)
    finally:
        _cleanup_user(db, user.id)
        db.close()


def test_monthly_due_date_jan_31_to_feb_28():
    start = date(2026, 1, 31)
    assert due_date_for_index(start, 1, "monthly") == start
    assert due_date_for_index(start, 2, "monthly") == date(2026, 2, 28)
    assert due_date_for_index(start, 3, "monthly") == date(2026, 3, 31)


def test_biweekly_due_dates():
    start = date(2026, 8, 1)
    assert due_date_for_index(start, 2, "biweekly") == date(2026, 8, 15)
    assert due_date_for_index(start, 3, "biweekly") == date(2026, 8, 29)


def test_parse_installment_count():
    assert parse_installment_count("12x") == 12
    assert parse_installment_count("6 vezes") == 6
    assert parse_installment_count("1x") is None


def test_parse_installment_start_index():
    assert parse_installment_start_index("1", 12) == 1
    assert parse_installment_start_index("primeira", 12) == 1
    assert parse_installment_start_index("3", 12) == 3
    assert parse_installment_start_index("3ª parcela", 12) == 3
    assert parse_installment_start_index("13", 12) is None


def test_installment_payment_date_keeps_competence_and_due():
    from app.services.transaction_slots import fill_slot
    from app.timezone import local_today

    wizard = {
        "tx_type": "expense",
        "payment_mode": "installment",
        "competence_date": "2026-09-30",
        "due_date": "2026-09-30",
        "payment_date": None,
    }
    fill_slot(wizard, "payment_date", "hoje", None, None)  # type: ignore[arg-type]
    today = local_today().isoformat()
    assert wizard["competence_date"] == "2026-09-30"
    assert wizard["due_date"] == "2026-09-30"
    assert wizard["payment_date"] == today
    assert wizard["transaction_date"] == today


def test_create_installment_plan_uses_due_as_schedule_anchor():
    from app.config import settings
    from app.timezone import local_today

    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"inst_dates_{suffix}@test.com",
        password="secret1",
        name="Inst Dates",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        account = _create_account(db, user.id, f"Conta_{suffix}")
        due = date(2026, 9, 30)
        pay = local_today()
        plan, txs = create_installment_plan(
            db,
            user.id,
            account_id=account["id"],
            category_id=None,
            tx_type="expense",
            total_cents=9500,
            installment_count=12,
            interval="monthly",
            start_date=due,
            description="Prestação",
            first_status="actual",
            competence_date=due,
            due_date=due,
            payment_date=pay,
            start_index=1,
        )
        assert plan.start_date == due
        first = txs[0]
        assert first.competence_date == due
        assert first.due_date == due
        assert first.payment_date == pay
        assert first.transaction_date == pay
        assert txs[1].due_date == date(2026, 10, 30)
    finally:
        _cleanup_user(db, user.id)
        db.close()


def test_create_installment_plan_start_index_partial():
    from app.config import settings

    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"inst_partial_{suffix}@test.com",
        password="secret1",
        name="Inst Partial",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        account = _create_account(db, user.id, f"Conta_{suffix}")
        start = date(2026, 10, 10)
        plan, txs = create_installment_plan(
            db,
            user.id,
            account_id=account["id"],
            category_id=None,
            tx_type="expense",
            total_cents=12000,
            installment_count=12,
            interval="monthly",
            start_date=start,
            description="Notebook",
            competence_date=start,
            due_date=start,
            start_index=3,
        )
        assert plan.installment_count == 12
        assert len(txs) == 10
        assert [tx.installment_index for tx in txs] == list(range(3, 13))
        assert txs[0].due_date == start
        assert txs[0].amount_cents == 1000
        assert txs[-1].installment_index == 12
    finally:
        _cleanup_user(db, user.id)
        db.close()


@pytest.mark.asyncio
async def test_installment_skips_date_inference_from_ontem():
    from app.config import settings
    from app.services.transaction_slots import WIZARD_KEY
    from app.services.transaction_wizard import try_process_transaction_wizard
    from app.timezone import local_today

    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"instontem_{suffix}@test.com",
        password="secret1",
        name="Wiz Ontem",
        is_active=True,
    )
    session: dict = {}
    yesterday = (local_today() - __import__("datetime").timedelta(days=1)).isoformat()
    try:
        finance.seed_defaults(db, user.id)
        finance.create_account(
            db,
            user.id,
            CreateAccountInput(name=f"Carteira_{suffix}", account_type="carteira"),
        )
        session[WIZARD_KEY] = {
            "tx_type": "expense",
            "status": None,
            "amount": "95",
            "description": "Prestação da casa",
            "account_name": f"Carteira_{suffix}",
            "category_name": None,
            "competence_date": None,
            "due_date": None,
            "payment_date": None,
            "transaction_date": yesterday,
            "payment_mode": None,
            "is_recurring": None,
            "frequency": None,
            "recurrence_end_date": None,
            "recurrence_end_asked": False,
            "installment_count": None,
            "installment_interval": None,
            "installment_start_index": None,
            "installment_amount_basis": None,
            "source_message": "Ontem tive a despesa de 95 referente a prestação da casa",
            "suggested_category": None,
        }
        try_process_transaction_wizard(session, "realizado", db=db, user_id=user.id)
        try_process_transaction_wizard(session, "parcelado", db=db, user_id=user.id)
        wizard = session[WIZARD_KEY]
        assert wizard["competence_date"] is None
        assert wizard["due_date"] is None
        try_process_transaction_wizard(session, "12", db=db, user_id=user.id)
        try_process_transaction_wizard(session, "mensal", db=db, user_id=user.id)
        result = try_process_transaction_wizard(session, "1", db=db, user_id=user.id)
        assert result is not None
        assert "competência" in result.message.lower() or "competencia" in result.message.lower()
        assert "parcela" in result.message.lower()
    finally:
        _cleanup_user(db, user.id)
        db.close()


@pytest.mark.asyncio
async def test_wizard_installment_asks_dates_after_start_index():
    from app.config import settings
    from app.services.transaction_wizard import begin_login_prompt, try_process_transaction_wizard

    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"instdate_{suffix}@test.com",
        password="secret1",
        name="Wiz Date",
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
        begin_login_prompt(session)
        try_process_transaction_wizard(session, "despesa", db=db, user_id=user.id)
        try_process_transaction_wizard(session, "realizado", db=db, user_id=user.id)
        try_process_transaction_wizard(session, "parcelado", db=db, user_id=user.id)
        try_process_transaction_wizard(session, "12x", db=db, user_id=user.id)
        try_process_transaction_wizard(session, "mensal", db=db, user_id=user.id)
        result = try_process_transaction_wizard(session, "3", db=db, user_id=user.id)
        assert result is not None
        assert "competência" in result.message.lower() or "competencia" in result.message.lower()
        result_comp = try_process_transaction_wizard(session, "10/10/2026", db=db, user_id=user.id)
        assert result_comp is not None
        assert "vencimento" in result_comp.message.lower()
    finally:
        _cleanup_user(db, user.id)
        db.close()


def test_register_installment_first_actual_rest_planned():
    from app.config import settings

    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"inst_{suffix}@test.com",
        password="secret1",
        name="Inst User",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        account = _create_account(db, user.id, f"Conta_{suffix}")
        start = date(2026, 8, 10)
        result = finance.register_expense(
            db,
            user.id,
            RegisterExpenseInput(
                amount="300",
                description="Notebook",
                account_name=account["name"],
                category_name="Lazer",
                competence_date=start,
                due_date=start,
                payment_date=start,
                status="actual",
                installment_count=3,
                installment_interval="monthly",
            ),
        )
        assert result["installment_plan_id"] is not None
        txs = db.scalars(
            select(Transaction).where(
                Transaction.installment_plan_id == result["installment_plan_id"]
            )
        ).all()
        assert len(txs) == 3
        assert txs[0].status == "actual"
        assert all(tx.status == "planned" for tx in txs[1:])
        assert sum(tx.amount_cents for tx in txs) == 30000
    finally:
        _cleanup_user(db, user.id)
        db.close()


def test_cancel_installment_plan_removes_only_planned():
    from app.config import settings

    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"inst2_{suffix}@test.com",
        password="secret1",
        name="Inst User 2",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        account = _create_account(db, user.id, f"Conta_{suffix}", opening_balance="5000")
        start = local_today()
        first = finance.register_expense(
            db,
            user.id,
            RegisterExpenseInput(
                amount="120",
                description="Curso",
                account_name=account["name"],
                category_name="Lazer",
                competence_date=start,
                due_date=start,
                status="planned",
                installment_count=4,
                installment_interval="monthly",
            ),
        )
        plan_id = first["installment_plan_id"]
        pending = db.scalars(
            select(Transaction).where(
                Transaction.installment_plan_id == plan_id,
                Transaction.status == "planned",
            )
        ).all()
        assert len(pending) == 4
        finance.realize_planned(
            db,
            user.id,
            RealizePlannedInput(planned_id=pending[0].id, payment_date=start),
        )
        before = db.scalar(
            select(func.count()).select_from(Transaction).where(
                Transaction.installment_plan_id == plan_id
            )
        )
        cancel_installment_plan(db, user.id, plan_id)
        after = db.scalar(
            select(func.count()).select_from(Transaction).where(
                Transaction.installment_plan_id == plan_id
            )
        )
        actual_count = db.scalar(
            select(func.count()).select_from(Transaction).where(
                Transaction.user_id == user.id,
                Transaction.status == "actual",
                Transaction.description.like("Curso%"),
            )
        )
        assert after < before
        assert after == 0
        assert actual_count >= 1
        plan = db.get(InstallmentPlan, plan_id)
        assert plan.is_active is False
    finally:
        _cleanup_user(db, user.id)
        db.close()


@pytest.mark.asyncio
async def test_wizard_installment_does_not_trigger_multi():
    from app.config import settings

    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"instwiz_{suffix}@test.com",
        password="secret1",
        name="Wiz Inst",
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
        from app.services.transaction_slots import WIZARD_KEY
        from app.services.transaction_wizard import begin_login_prompt, try_process_transaction_wizard

        begin_login_prompt(session)
        try_process_transaction_wizard(session, "despesa", db=db, user_id=user.id)
        try_process_transaction_wizard(session, "previsto", db=db, user_id=user.id)
        try_process_transaction_wizard(session, "agosto", db=db, user_id=user.id)
        try_process_transaction_wizard(session, "10/08/2026", db=db, user_id=user.id)

        with patch("app.agent.runner.call_intent_llm", new_callable=AsyncMock) as mock_llm:
            result = await process_message(db, user.id, "parcelado", session=session)

        assert "vezes" in result.message.lower() or "parcela" in result.message.lower()
        mock_llm.assert_not_called()

        with patch("app.agent.runner.call_intent_llm", new_callable=AsyncMock) as mock_llm2:
            result2 = await process_message(db, user.id, "12x", session=session)

        assert (
            "intervalo" in result2.message.lower()
            or "mensal" in result2.message.lower()
            or "quinzenal" in result2.message.lower()
        )
        mock_llm2.assert_not_called()
    finally:
        _cleanup_user(db, user.id)
        db.close()


@pytest.mark.asyncio
async def test_wizard_asks_installment_amount_basis():
    from app.config import settings
    from app.services.transaction_slots import WIZARD_KEY
    from app.services.transaction_wizard import begin_login_prompt, try_process_transaction_wizard

    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"instbasis_{suffix}@test.com",
        password="secret1",
        name="Wiz Basis",
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
        begin_login_prompt(session)
        try_process_transaction_wizard(session, "despesa", db=db, user_id=user.id)
        try_process_transaction_wizard(session, "previsto", db=db, user_id=user.id)
        try_process_transaction_wizard(session, "agosto", db=db, user_id=user.id)
        try_process_transaction_wizard(session, "10/08/2026", db=db, user_id=user.id)
        try_process_transaction_wizard(session, "parcelado", db=db, user_id=user.id)
        try_process_transaction_wizard(session, "12x", db=db, user_id=user.id)
        result = try_process_transaction_wizard(session, "mensal", db=db, user_id=user.id)
        assert result is not None
        result_start = try_process_transaction_wizard(session, "1", db=db, user_id=user.id)
        assert result_start is not None
        wizard = session[WIZARD_KEY]
        assert wizard.get("competence_date") is not None
        assert wizard.get("due_date") is not None
        assert "competência" not in (result_start.message or "").lower()
        result_amount = try_process_transaction_wizard(session, "1200", db=db, user_id=user.id)
        assert result_amount is not None
        msg = result_amount.message.lower()
        assert "total" in msg
        assert "parcela" in msg
        assert "Valor total" in (result_amount.suggestions or [])
        assert "Valor da parcela" in (result_amount.suggestions or [])
    finally:
        _cleanup_user(db, user.id)
        db.close()


@pytest.mark.asyncio
async def test_wizard_installment_basis_creates_equal_installments():
    from app.config import settings
    from app.services.transaction_wizard import begin_login_prompt, try_process_transaction_wizard

    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"instconf_{suffix}@test.com",
        password="secret1",
        name="Wiz Conf",
        is_active=True,
    )
    session: dict = {}
    account_name = f"Carteira_{suffix}"
    try:
        finance.seed_defaults(db, user.id)
        finance.create_account(
            db,
            user.id,
            CreateAccountInput(name=account_name, account_type="carteira"),
        )
        begin_login_prompt(session)
        steps = [
            "despesa",
            "previsto",
            "agosto",
            "10/08/2026",
            "parcelado",
            "12x",
            "mensal",
            "1",
            "1200",
            "Valor da parcela",
            "notebook",
            "Lazer",
        ]
        confirmed = None
        for step in steps:
            result = try_process_transaction_wizard(session, step, db=db, user_id=user.id)
            if result and result.needs_confirmation:
                confirmed = result
                break
        assert confirmed is not None
        assert confirmed.pending_action["arguments"]["installment_amount_basis"] == "installment"
        finance.register_expense(
            db,
            user.id,
            RegisterExpenseInput(**confirmed.pending_action["arguments"]),
        )
        plan_id = db.scalars(
            select(Transaction.installment_plan_id)
            .where(Transaction.user_id == user.id)
            .limit(1)
        ).first()
        txs = db.scalars(
            select(Transaction).where(Transaction.installment_plan_id == plan_id)
        ).all()
        assert len(txs) == 12
        assert all(tx.amount_cents == 120000 for tx in txs)
    finally:
        _cleanup_user(db, user.id)
        db.close()
