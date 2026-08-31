import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import create_user
from app.models import Account, Category, Transaction, User
from app.schemas import RegisterExpenseInput, UpdateTransactionInput
from app.services.finance import register_expense, update_transaction
from tests.test_transaction_slots import _create_account, _setup_user


def test_update_transaction_changes_account():
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"update_{suffix}@test.com",
        password="secret1",
        name="Update User",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        carteira = _create_account(db, user.id, f"Carteira_{suffix}")
        mercado = _create_account(db, user.id, f"Mercado_{suffix}")

        register_expense(
            db,
            user.id,
            RegisterExpenseInput(
                amount="40.50",
                description="passagem",
                account_name=carteira["name"],
                category_name="Transporte",
            ),
        )

        result = update_transaction(
            db,
            user.id,
            UpdateTransactionInput(
                description="passagem",
                amount="40.50",
                account_name=mercado["name"],
            ),
        )

        assert result["account"] == mercado["name"]
        assert result["amount"] in {"40.50", "40.5", "40,50"}
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()
