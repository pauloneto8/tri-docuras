import uuid
from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.auth import create_user, read_scope_id
from app.config import settings
from app.models import Account, Category, Transaction, User
from app.schemas import ListTransactionsInput, TransactionCreate
from app.services import admin, finance


def test_read_scope_for_regular_user():
    from app.config import settings as cfg

    engine = create_engine(cfg.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"regular_{suffix}@example.com",
        password="secret1",
        name="Regular",
    )
    try:
        assert read_scope_id(user) == user.id
        assert user.is_root is False
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(
            synchronize_session=False
        )
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_root_personal_scope_excludes_other_users():
    from app.config import settings as cfg

    engine = create_engine(cfg.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    root_email = f"root_{suffix}@example.com"
    settings.root_emails = root_email
    user = create_user(db, email=root_email, password="secret1", name="Root")
    other = create_user(
        db,
        email=f"other_{suffix}@example.com",
        password="secret2",
        name="Other",
        is_active=True,
    )
    try:
        finance.seed_defaults(db, user.id)
        finance.complete_onboarding(db, user.id, name="Conta Root", opening_balance="0")
        finance.seed_defaults(db, other.id)
        finance.complete_onboarding(db, other.id, name="Conta Other", opening_balance="0")
        other_account = db.scalars(select(Account).where(Account.user_id == other.id)).first()
        finance.create_transaction(
            db,
            other.id,
            TransactionCreate(
                account_id=other_account.id,
                category_id=None,
                type="expense",
                amount_cents=1000,
                description="Compra teste",
                transaction_date=date.today(),
            ),
        )
        assert user.is_root is True
        assert read_scope_id(user) == user.id

        personal_txs = finance.list_transactions(
            db, read_scope_id(user), ListTransactionsInput(limit=100)
        )
        assert all(tx.get("description") != "Compra teste" for tx in personal_txs)

        global_txs = finance.list_transactions(db, None, ListTransactionsInput(limit=100))
        emails = {tx.get("user_email") for tx in global_txs}
        assert other.email in emails

        detail = admin.get_user_detail(db, other.id)
        assert detail["profile"]["email"] == other.email
        assert any(tx["description"] == "Compra teste" for tx in detail["transactions"])
        assert any(acc["account"] == "Conta Other" for acc in detail["accounts"])
    finally:
        db.query(Transaction).filter(Transaction.user_id.in_([user.id, other.id])).delete(
            synchronize_session=False
        )
        db.query(Account).filter(Account.user_id.in_([user.id, other.id])).delete(
            synchronize_session=False
        )
        db.query(Category).filter(Category.user_id.in_([user.id, other.id])).delete(
            synchronize_session=False
        )
        db.query(User).filter(User.id.in_([user.id, other.id])).delete(synchronize_session=False)
        db.commit()
        db.close()
