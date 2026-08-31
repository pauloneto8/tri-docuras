import uuid
from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import create_user
from app.config import settings
from app.models import Account, Category, Transaction, User
from app.schemas import CreateAccountInput, RegisterExpenseInput, RegisterIncomeInput, SummaryInput
from app.services import finance


def _setup(db, user):
    finance.seed_defaults(db, user.id)


def _create_account(
    db,
    user_id,
    name,
    opening_balance="0",
    opening_balance_date=date(2000, 1, 1),
):
    opening_date = None
    if opening_balance and opening_balance.strip() not in {"0", "0,00", "0.00"}:
        opening_date = opening_balance_date
    return finance.create_account(
        db,
        user_id,
        CreateAccountInput(
            name=name,
            account_type="corrente",
            opening_balance=opening_balance,
            opening_balance_date=opening_date,
        ),
    )


def _cleanup(db, user):
    db.query(Transaction).filter(Transaction.user_id == user.id).delete(
        synchronize_session=False
    )
    db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
    db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
    db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
    db.commit()
    db.close()


def test_summary_includes_opening_balance_in_previous_and_total():
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    db = Session()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"sum_{suffix}@test.com",
        password="pass",
        name="Sum User",
        is_active=True,
    )
    try:
        _setup(db, user)
        _create_account(db, user.id, f"Conta_{suffix}", opening_balance="889,63")

        summary = finance.get_summary(db, user.id, SummaryInput())

        assert summary["balance"] in {"0", "0.00", "0,00"}
        assert summary["previous_balance"] == "889,63"
        assert summary["ending_balance"] == "889,63"
        assert summary["total_balance"] == "889,63"
        assert summary["total_balance_cents"] == 88963
    finally:
        _cleanup(db, user)


def test_monthly_previous_balance_includes_prior_month_transactions():
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    db = Session()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"sum_{suffix}@test.com",
        password="pass",
        name="Sum User",
        is_active=True,
    )
    try:
        _setup(db, user)
        account = _create_account(db, user.id, f"Conta_{suffix}", opening_balance="1000")
        ref = date(2026, 8, 15)
        finance.register_expense(
            db,
            user.id,
            RegisterExpenseInput(
                amount="200",
                description="Julho",
                account_name=account["name"],
                category_name="Outros",
                transaction_date=date(2026, 7, 31),
            ),
        )
        finance.register_income(
            db,
            user.id,
            RegisterIncomeInput(
                amount="50",
                description="Agosto",
                account_name=account["name"],
                category_name="Salário",
                transaction_date=date(2026, 8, 10),
            ),
        )

        summary = finance.get_summary(
            db, user.id, SummaryInput(period="month", ref_date=ref)
        )

        assert summary["previous_balance_cents"] == 100000 - 20000
        assert summary["income_cents"] == 5000
        assert summary["expense_cents"] == 0
        assert summary["balance_cents"] == 5000
        assert summary["ending_balance_cents"] == 100000 - 20000 + 5000
    finally:
        _cleanup(db, user)


def test_daily_previous_balance_uses_yesterday():
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    db = Session()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"sum_{suffix}@test.com",
        password="pass",
        name="Sum User",
        is_active=True,
    )
    try:
        _setup(db, user)
        account = _create_account(db, user.id, f"Conta_{suffix}", opening_balance="500")
        today = date(2026, 8, 30)
        yesterday = today - timedelta(days=1)
        finance.register_expense(
            db,
            user.id,
            RegisterExpenseInput(
                amount="30",
                description="Ontem",
                account_name=account["name"],
                category_name="Outros",
                transaction_date=yesterday,
            ),
        )
        finance.register_income(
            db,
            user.id,
            RegisterIncomeInput(
                amount="100",
                description="Hoje",
                account_name=account["name"],
                category_name="Salário",
                transaction_date=today,
            ),
        )

        summary = finance.get_summary(
            db, user.id, SummaryInput(period="day", ref_date=today)
        )

        assert summary["previous_balance_cents"] == 50000 - 3000
        assert summary["income_cents"] == 10000
        assert summary["expense_cents"] == 0
        assert summary["ending_balance_cents"] == 50000 - 3000 + 10000
    finally:
        _cleanup(db, user)


def test_weekly_previous_balance_uses_prior_week():
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    db = Session()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"sum_{suffix}@test.com",
        password="pass",
        name="Sum User",
        is_active=True,
    )
    try:
        _setup(db, user)
        account = _create_account(db, user.id, f"Conta_{suffix}", opening_balance="1000")
        # Semana de 25/08 (seg) a 31/08 (dom) de 2026
        ref = date(2026, 8, 27)
        finance.register_expense(
            db,
            user.id,
            RegisterExpenseInput(
                amount="80",
                description="Semana passada",
                account_name=account["name"],
                category_name="Outros",
                transaction_date=date(2026, 8, 22),
            ),
        )
        finance.register_income(
            db,
            user.id,
            RegisterIncomeInput(
                amount="120",
                description="Esta semana",
                account_name=account["name"],
                category_name="Salário",
                transaction_date=date(2026, 8, 26),
            ),
        )

        summary = finance.get_summary(
            db, user.id, SummaryInput(period="week", ref_date=ref)
        )

        assert summary["previous_balance_cents"] == 100000 - 8000
        assert summary["income_cents"] == 12000
        assert summary["expense_cents"] == 0
        assert summary["ending_balance_cents"] == 100000 - 8000 + 12000
    finally:
        _cleanup(db, user)


def test_resolve_period_bounds_week_iso():
    # 30/08/2026 é domingo; semana ISO começa na segunda 24/08
    start, end = finance.resolve_period_bounds("week", date(2026, 8, 30))
    assert start == date(2026, 8, 24)
    assert end == date(2026, 8, 30)


def test_opening_balance_ignored_before_declaration_date():
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    db = Session()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"sum_{suffix}@test.com",
        password="pass",
        name="Sum User",
        is_active=True,
    )
    try:
        _setup(db, user)
        account = _create_account(
            db,
            user.id,
            f"Conta_{suffix}",
            opening_balance="889,63",
            opening_balance_date=date(2026, 8, 1),
        )
        finance.register_expense(
            db,
            user.id,
            RegisterExpenseInput(
                amount="50",
                description="Agosto",
                account_name=account["name"],
                category_name="Outros",
                transaction_date=date(2026, 8, 10),
            ),
        )

        june = finance.get_summary(
            db, user.id, SummaryInput(period="month", ref_date=date(2026, 6, 1))
        )
        august = finance.get_summary(
            db, user.id, SummaryInput(period="month", ref_date=date(2026, 8, 15))
        )

        assert june["previous_balance_cents"] == 0
        assert june["ending_balance_cents"] == 0
        assert august["previous_balance_cents"] == 0
        assert august["expense_cents"] == 5000
        assert august["ending_balance_cents"] == 88963 - 5000

        july_balances = finance.account_balances(
            db, user.id, as_of=date(2026, 7, 31)
        )
        august_balances = finance.account_balances(
            db, user.id, as_of=date(2026, 8, 31)
        )
        assert all(item["balance_cents"] == 0 for item in july_balances)
        assert sum(item["balance_cents"] for item in august_balances) == 88963 - 5000
    finally:
        _cleanup(db, user)
