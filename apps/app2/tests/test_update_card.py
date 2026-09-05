import uuid

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.auth import create_user
from app.models import Account, CardInvoice, Category, CreditCard, Transaction, User
from app.schemas import CreateAccountInput, CreateCardInput, UpdateCardInput
from app.services import finance
from app.services.tools import try_rule_based_parse


def test_update_card_due_day():
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"upd_card_{suffix}@test.com",
        password="secret1",
        name="Card User",
        is_active=True,
    )
    try:
        finance.seed_defaults(db, user.id)
        debit = finance.create_account(
            db,
            user.id,
            CreateAccountInput(
                name=f"Corrente_{suffix}",
                account_type="corrente",
                opening_balance="0",
            ),
        )
        finance.create_card(
            db,
            user.id,
            CreateCardInput(
                name=f"Nubank_{suffix}",
                closing_day=10,
                due_day=17,
                settlement_account_name=debit["name"],
            ),
        )

        result = finance.update_card(
            db,
            user.id,
            UpdateCardInput(
                card_name=f"Nubank_{suffix}",
                due_day=20,
            ),
        )

        assert result["due_day"] == 20
        assert result["closing_day"] == 10

        card = db.scalar(
            select(CreditCard).where(
                CreditCard.user_id == user.id,
                CreditCard.name == f"Nubank_{suffix}",
            )
        )
        assert card is not None
        assert card.due_day == 20
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(CardInvoice).filter(CardInvoice.user_id == user.id).delete(synchronize_session=False)
        db.query(CreditCard).filter(CreditCard.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_rule_based_update_card_due_day():
    tool = try_rule_based_parse(
        "Altere o vencimento do cartão Nubank para dia 20"
    )
    assert tool is not None
    assert tool.tool == "update_card"
    assert tool.arguments.get("card_name") == "Nubank"
    assert tool.arguments.get("due_day") == 20


def test_deactivate_card():
    from app.config import settings
    from app.schemas import DeleteCardInput

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"del_card_{suffix}@test.com",
        password="secret1",
        name="Card User",
        is_active=True,
    )
    try:
        finance.seed_defaults(db, user.id)
        debit = finance.create_account(
            db,
            user.id,
            CreateAccountInput(
                name=f"Corrente_{suffix}",
                account_type="corrente",
                opening_balance="0",
            ),
        )
        finance.create_card(
            db,
            user.id,
            CreateCardInput(
                name=f"Itaú_{suffix}",
                closing_day=5,
                due_day=15,
                settlement_account_name=debit["name"],
            ),
        )

        result = finance.deactivate_card(
            db,
            user.id,
            DeleteCardInput(card_name=f"Itaú_{suffix}"),
        )
        assert result["name"] == f"Itaú_{suffix}"
        assert result["is_active"] is False

        card = db.scalar(
            select(CreditCard).where(
                CreditCard.user_id == user.id,
                CreditCard.name == f"Itaú_{suffix}",
            )
        )
        assert card is not None
        assert card.is_active is False
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(CardInvoice).filter(CardInvoice.user_id == user.id).delete(synchronize_session=False)
        db.query(CreditCard).filter(CreditCard.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_rule_based_delete_card():
    tool = try_rule_based_parse("Excluir cartão Nubank")
    assert tool is not None
    assert tool.tool == "delete_card"
    assert tool.arguments.get("card_name") == "Nubank"
