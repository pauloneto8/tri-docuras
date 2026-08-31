import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import create_user
from app.models import Account, Category, User
from app.schemas import CreateAccountInput, UpdateAccountInput
from app.services import finance
from app.services.tools import try_rule_based_parse


def test_update_account_opening_balance():
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"upd_acc_{suffix}@test.com",
        password="secret1",
        name="Account User",
        is_active=True,
    )
    try:
        finance.seed_defaults(db, user.id)
        finance.create_account(
            db,
            user.id,
            CreateAccountInput(
                name="Mercado Pago",
                account_type="corrente",
                institution="Mercado Pago",
                opening_balance="0",
            ),
        )

        result = finance.update_account(
            db,
            user.id,
            UpdateAccountInput(
                account_name="Mercado Pago",
                opening_balance="889,63",
            ),
        )

        assert result["name"] == "Mercado Pago"
        assert result["opening_balance"] in {"889.63", "889,63"}
    finally:
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_rule_based_opening_balance_correction():
    tool = try_rule_based_parse(
        "A conta Mercado Pago tem saldo inicial de 889,63. Altere"
    )
    assert tool is not None
    assert tool.tool == "update_account"
    assert tool.arguments.get("account_name") == "Mercado Pago"
    assert tool.arguments.get("opening_balance") == "889.63"


def test_update_account_opening_balance_date():
    from datetime import date

    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"upd_date_{suffix}@test.com",
        password="secret1",
        name="Account User",
        is_active=True,
    )
    try:
        finance.seed_defaults(db, user.id)
        finance.create_account(
            db,
            user.id,
            CreateAccountInput(
                name="Mercado Pago",
                account_type="corrente",
                opening_balance="500",
                opening_balance_date=date(2026, 8, 30),
            ),
        )

        result = finance.update_account(
            db,
            user.id,
            UpdateAccountInput(
                account_name="Mercado Pago",
                opening_balance_date=date(2026, 8, 1),
            ),
        )

        assert result["opening_balance_date"] == "2026-08-01"
        assert result["opening_balance_date_label"] == "01/08/2026"
    finally:
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_rule_based_opening_balance_date_correction():
    from app.services.tools import parse_opening_balance_date

    assert parse_opening_balance_date("1 de agosto de 2026") == "2026-08-01"
    assert parse_opening_balance_date("01/08/2026") == "2026-08-01"

    tool = try_rule_based_parse(
        "Altere a data do saldo inicial da conta Mercado Pago para 1 de agosto de 2026"
    )
    assert tool is not None
    assert tool.tool == "update_account"
    assert tool.arguments.get("account_name") == "Mercado Pago"
    assert tool.arguments.get("opening_balance_date") == "2026-08-01"
