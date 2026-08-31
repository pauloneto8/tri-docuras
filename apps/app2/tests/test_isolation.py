import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.auth import create_user
from app.models import Account, Category, Transaction, User
from app.schemas import ListTransactionsInput, RegisterExpenseInput
from app.services import finance


@pytest.fixture
def db_session():
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_user_data_isolation(db_session: Session):
    suffix = uuid.uuid4().hex[:8]
    user_a = create_user(
        db_session,
        email=f"isol_a_{suffix}@example.com",
        password="secret1",
        name="User A",
        is_active=True,
    )
    user_b = create_user(
        db_session,
        email=f"isol_b_{suffix}@example.com",
        password="secret2",
        name="User B",
        is_active=True,
    )

    finance.seed_defaults(db_session, user_a.id)
    finance.complete_onboarding(db_session, user_a.id, name="Conta A", opening_balance="0")
    finance.seed_defaults(db_session, user_b.id)
    finance.complete_onboarding(db_session, user_b.id, name="Conta B", opening_balance="0")

    finance.register_expense(
        db_session,
        user_a.id,
        RegisterExpenseInput(
            amount="100",
            description="mercado user A",
            account_name="Conta A",
            category_name="Alimentação",
        ),
    )

    txs_a = finance.list_transactions(db_session, user_a.id, ListTransactionsInput(limit=10))
    txs_b = finance.list_transactions(db_session, user_b.id, ListTransactionsInput(limit=10))

    assert len(txs_a) == 1
    assert txs_a[0]["description"] == "Mercado user A"
    assert len(txs_b) == 0

    count_b = db_session.scalar(
        select(Transaction).where(
            Transaction.user_id == user_b.id,
            Transaction.description == "mercado user A",
        )
    )
    assert count_b is None

    db_session.query(Transaction).filter(
        Transaction.user_id.in_([user_a.id, user_b.id])
    ).delete(synchronize_session=False)
    db_session.query(Account).filter(
        Account.user_id.in_([user_a.id, user_b.id])
    ).delete(synchronize_session=False)
    db_session.query(Category).filter(
        Category.user_id.in_([user_a.id, user_b.id])
    ).delete(synchronize_session=False)
    db_session.query(User).filter(User.id.in_([user_a.id, user_b.id])).delete(
        synchronize_session=False
    )
    db_session.commit()
