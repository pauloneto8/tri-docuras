import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import create_user
from app.models import Account, Category, Transaction, User
from app.schemas import RegisterTransferInput, UpdateTransferInput
from app.services.finance import register_transfer, update_transfer
from app.services.tools import try_rule_based_parse
from tests.test_transaction_slots import _create_account, _setup_user


def test_correction_transfer_uses_update_transfer():
    tool = try_rule_based_parse(
        "Corrija a transferência de 594. O correto é de Flash para o mercado Pago"
    )
    assert tool is not None
    assert tool.tool == "update_transfer"
    assert tool.arguments.get("amount") == "594"
    assert tool.arguments.get("from_account_name") == "Flash"
    assert "mercado" in tool.arguments.get("to_account_name", "").lower()


def test_update_transfer_swaps_accounts():
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"upd_xfer_{suffix}@test.com",
        password="secret1",
        name="Xfer User",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        flash = _create_account(db, user.id, f"Flash_{suffix}")
        mercado = _create_account(db, user.id, f"Mercado Pago_{suffix}")

        register_transfer(
            db,
            user.id,
            RegisterTransferInput(
                amount="594",
                from_account_name=mercado["name"],
                to_account_name=flash["name"],
            ),
        )

        result = update_transfer(
            db,
            user.id,
            UpdateTransferInput(
                amount="594",
                from_account_name=flash["name"],
                to_account_name=mercado["name"],
            ),
        )

        assert result["from_account"] == flash["name"]
        assert result["to_account"] == mercado["name"]
        assert result["amount"] in {"594", "594.00", "594,00"}
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()
