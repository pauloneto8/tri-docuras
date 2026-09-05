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


def test_update_transaction_description_by_amount():
    """Corrigir descrição: amount identifica; description é o novo texto."""
    from app.config import settings
    from app.schemas import RegisterIncomeInput
    from app.services.finance import register_income
    from app.services.installments import create_installment_plan
    from sqlalchemy import select

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"upd_desc_{suffix}@test.com",
        password="secret1",
        name="Upd Desc",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        flash = _create_account(db, user.id, f"Flash_{suffix}")
        cat = db.scalar(
            select(Category).where(Category.user_id == user.id, Category.type == "income")
        )
        plan, txs = create_installment_plan(
            db,
            user.id,
            account_id=flash["id"],
            category_id=cat.id,
            tx_type="income",
            total_cents=59400,
            installment_count=3,
            interval="monthly",
            start_date=__import__("datetime").date(2026, 9, 1),
            description="Lance uma receita de",
            first_status="planned",
            amount_basis="installment",
            start_index=1,
        )
        db.commit()

        result = update_transaction(
            db,
            user.id,
            UpdateTransactionInput(
                amount="594",
                description="Auxílio transporte",
            ),
        )
        assert "auxílio" in result["description"].lower() or "transporte" in result[
            "description"
        ].lower()

        refreshed = db.scalars(
            select(Transaction).where(
                Transaction.user_id == user.id,
                Transaction.installment_plan_id == plan.id,
            )
        ).all()
        assert len(refreshed) == 3
        for tx in refreshed:
            assert tx.description.startswith("Auxílio transporte") or tx.description.startswith(
                "Auxilio transporte"
            )
            assert f"{tx.installment_index}/3" in tx.description
    finally:
        from app.models import InstallmentPlan

        db.query(Transaction).filter(Transaction.user_id == user.id).delete(
            synchronize_session=False
        )
        db.query(InstallmentPlan).filter(InstallmentPlan.user_id == user.id).delete(
            synchronize_session=False
        )
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_rule_parse_update_description_para():
    from app.services.tools import try_rule_based_parse

    tool = try_rule_based_parse(
        "Atualiza a descrição na receita de 594 para auxílio transporte"
    )
    assert tool is not None
    assert tool.tool == "update_transaction"
    assert tool.arguments.get("amount") == "594"
    assert "transporte" in tool.arguments.get("description", "").lower()


def test_rule_parse_update_description_and_invoice_month():
    from app.services.tools import try_rule_based_parse

    tool = try_rule_based_parse(
        "Corrija a despesa de 17,54 para Camisa de amigo secreto na fatura de setembro"
    )
    assert tool is not None
    assert tool.tool == "update_transaction"
    assert tool.arguments.get("amount") == "17.54" or tool.arguments.get("amount") == "17,54"
    assert "amigo" in tool.arguments.get("description", "").lower()
    assert "fatura" not in tool.arguments.get("description", "").lower()
    assert tool.arguments.get("invoice_due_month") == 9
