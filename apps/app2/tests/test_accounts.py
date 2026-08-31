import uuid

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.auth import create_user
from app.models import Account, Category, Transaction, User
from app.schemas import CreateAccountInput
from app.services import finance


def _setup_user(db, user):
    finance.seed_defaults(db, user.id)
    finance.complete_onboarding(db, user.id, name="Principal", opening_balance="0")


def test_create_account_via_finance():
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"acct_page_{suffix}@example.com",
        password="secret1",
        name="User Page",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        result = finance.create_account(
            db,
            user.id,
            CreateAccountInput(
                name=f"Nubank_{suffix}",
                account_type="corrente",
                institution="Nubank",
                opening_balance="500",
            ),
        )
        assert result["name"] == f"Nubank_{suffix}"
        balances = finance.account_balances(db, user.id)
        names = [b["account"] for b in balances]
        assert f"Nubank_{suffix}" in names
        nubank = next(b for b in balances if b["account"] == f"Nubank_{suffix}")
        assert nubank["balance_cents"] == 50000
        assert nubank["account_type_label"] == "Corrente"
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(
            synchronize_session=False
        )
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_deactivate_account():
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"deact_{suffix}@example.com",
        password="secret1",
        name="User Deact",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        second = finance.create_account(
            db,
            user.id,
            CreateAccountInput(name=f"Extra_{suffix}", account_type="poupanca"),
        )
        finance.deactivate_account(db, user.id, second["id"])
        active = db.scalars(
            select(Account).where(Account.user_id == user.id, Account.is_active.is_(True))
        ).all()
        names = [a.name for a in active]
        assert f"Extra_{suffix}" not in names
        assert "Principal" in names
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(
            synchronize_session=False
        )
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_cannot_deactivate_only_account():
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"only_{suffix}@example.com",
        password="secret1",
        name="User Only",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        principal = db.scalar(
            select(Account).where(Account.user_id == user.id, Account.name == "Principal")
        )
        try:
            finance.deactivate_account(db, user.id, principal.id)
            assert False, "should raise"
        except ValueError as exc:
            assert "única conta" in str(exc).lower()
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(
            synchronize_session=False
        )
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()
