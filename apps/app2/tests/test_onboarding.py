import uuid

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.auth import create_user
from app.models import Account, Category, Transaction, User
from app.services import finance


def test_complete_onboarding_creates_primary_account():
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"onboard_{suffix}@example.com",
        password="secret1",
        name="Onboard User",
        is_active=True,
    )
    try:
        finance.seed_defaults(db, user.id)
        assert user.onboarding_completed is False
        account = finance.complete_onboarding(
            db,
            user.id,
            name="Minha Carteira",
            opening_balance="150,50",
        )
        db.refresh(user)
        assert user.onboarding_completed is True
        assert account.name == "Minha Carteira"
        primary = finance.get_primary_account(db, user.id)
        assert primary is not None
        assert primary.name == "Minha Carteira"
        balances = finance.account_balances(db, user.id)
        wallet = next(b for b in balances if b["account"] == "Minha Carteira")
        assert wallet["balance_cents"] == 15050
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_complete_onboarding_saves_opening_balance_date_with_zero_balance():
    from datetime import date

    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"onboard_date_{suffix}@example.com",
        password="secret1",
        name="Onboard Date User",
        is_active=True,
    )
    try:
        finance.seed_defaults(db, user.id)
        account = finance.complete_onboarding(
            db,
            user.id,
            name="Minha Carteira",
            opening_balance="0",
            opening_balance_date=date(2026, 8, 1),
        )
        db.refresh(account)
        assert account.opening_balance_cents == 0
        assert account.opening_balance_date == date(2026, 8, 1)
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_complete_onboarding_saves_opening_balance_date_with_positive_balance():
    from datetime import date

    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"onboard_date2_{suffix}@example.com",
        password="secret1",
        name="Onboard Date User 2",
        is_active=True,
    )
    try:
        finance.seed_defaults(db, user.id)
        account = finance.complete_onboarding(
            db,
            user.id,
            name="Nubank",
            opening_balance="250,00",
            opening_balance_date=date(2026, 7, 15),
        )
        db.refresh(account)
        assert account.opening_balance_cents == 25000
        assert account.opening_balance_date == date(2026, 7, 15)
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_seed_defaults_does_not_create_account():
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"seed_{suffix}@example.com",
        password="secret1",
        name="Seed User",
        is_active=True,
    )
    try:
        finance.seed_defaults(db, user.id)
        accounts = db.scalars(select(Account).where(Account.user_id == user.id)).all()
        categories = db.scalars(select(Category).where(Category.user_id == user.id)).all()
        assert len(accounts) == 0
        assert len(categories) == 9
    finally:
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()
