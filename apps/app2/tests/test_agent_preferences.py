import uuid
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import create_user
from app.config import settings
from app.models import AgentDescriptionPreference, Category, CreditCard, Account, Transaction, User
from app.schemas import CreateAccountInput, RegisterExpenseInput
from app.services import finance
from app.services.agent_preferences import (
    lookup_description_preference,
    offer_description_preference_from_result,
    try_process_pending_description_preference,
)

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine)


def _setup_user(db, user):
    finance.seed_defaults(db, user.id)


def _cleanup(db, user_id):
    db.query(AgentDescriptionPreference).filter(
        AgentDescriptionPreference.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(Transaction).filter(Transaction.user_id == user_id).delete(
        synchronize_session=False
    )
    db.query(CreditCard).filter(CreditCard.user_id == user_id).delete(
        synchronize_session=False
    )
    db.query(Account).filter(Account.user_id == user_id).delete(synchronize_session=False)
    db.query(Category).filter(Category.user_id == user_id).delete(synchronize_session=False)
    db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
    db.commit()


def _register_expense(db, user_id, *, description, category_name, account_name=None, card_name=None):
    payload = RegisterExpenseInput(
        amount="50.00",
        description=description,
        category_name=category_name,
        account_name=account_name,
        card_name=card_name,
        status="actual",
    )
    return finance.register_expense(db, user_id, payload)


def test_offer_fires_only_on_exact_third_repetition():
    db = SessionLocal()
    email = f"{uuid.uuid4()}@example.com"
    user = create_user(db, email=email, password="Senha123!", name="Teste")
    _setup_user(db, user)
    account = finance.create_account(
        db,
        user.id,
        CreateAccountInput(
            name="Conta Teste",
            account_type="corrente",
            opening_balance="1000",
            opening_balance_date=date(2026, 1, 1),
        ),
    )
    category_name = "Alimentação"

    try:
        session: dict = {}
        result = None
        for i in range(3):
            result = _register_expense(
                db, user.id, description="ifood", category_name=category_name, account_name=account["name"]
            )
            offer = offer_description_preference_from_result(
                db, session, user.id, "register_expense", result
            )
            if i < 2:
                assert offer is None, f"não deveria oferecer na repetição {i + 1}"
            else:
                assert offer is not None
                assert "ifood" in offer.lower()
                assert session.get("pending_description_preference")

        # 4ª repetição: já não tem mais o pending (foi respondido ou não) e a
        # contagem passou de 3, então não oferece de novo.
        session.pop("pending_description_preference", None)
        result = _register_expense(
            db, user.id, description="ifood", category_name=category_name, account_name=account["name"]
        )
        offer_again = offer_description_preference_from_result(
            db, session, user.id, "register_expense", result
        )
        assert offer_again is None
    finally:
        _cleanup(db, user.id)
        db.close()


def test_confirm_yes_saves_preference_and_is_read_back():
    db = SessionLocal()
    email = f"{uuid.uuid4()}@example.com"
    user = create_user(db, email=email, password="Senha123!", name="Teste")
    _setup_user(db, user)
    account = finance.create_account(
        db,
        user.id,
        CreateAccountInput(
            name="Conta Teste",
            account_type="corrente",
            opening_balance="1000",
            opening_balance_date=date(2026, 1, 1),
        ),
    )
    try:
        session: dict = {}
        result = None
        for _ in range(3):
            result = _register_expense(
                db, user.id, description="uber", category_name="Transporte", account_name=account["name"]
            )
            offer_description_preference_from_result(db, session, user.id, "register_expense", result)

        assert session.get("pending_description_preference")
        assert lookup_description_preference(db, user.id, "uber") is None

        response = try_process_pending_description_preference(session, "sim", db, user.id)
        assert response is not None
        assert "pending_description_preference" not in session

        pref = lookup_description_preference(db, user.id, "uber")
        assert pref is not None
        assert pref.category_id == result["category_id"]
        assert pref.account_id == account["id"]
    finally:
        _cleanup(db, user.id)
        db.close()


def test_confirm_no_does_not_save_and_does_not_ask_again():
    db = SessionLocal()
    email = f"{uuid.uuid4()}@example.com"
    user = create_user(db, email=email, password="Senha123!", name="Teste")
    _setup_user(db, user)
    account = finance.create_account(
        db,
        user.id,
        CreateAccountInput(
            name="Conta Teste",
            account_type="corrente",
            opening_balance="1000",
            opening_balance_date=date(2026, 1, 1),
        ),
    )
    try:
        session: dict = {}
        for _ in range(3):
            result = _register_expense(
                db, user.id, description="farmacia popular", category_name="Saúde", account_name=account["name"]
            )
            offer_description_preference_from_result(db, session, user.id, "register_expense", result)

        assert session.get("pending_description_preference")
        response = try_process_pending_description_preference(session, "não", db, user.id)
        assert response is not None
        assert "pending_description_preference" not in session
        assert lookup_description_preference(db, user.id, "farmacia popular") is None

        # 4ª repetição não pergunta de novo (contagem já passou de 3).
        result = _register_expense(
            db, user.id, description="farmacia popular", category_name="Saúde", account_name=account["name"]
        )
        offer = offer_description_preference_from_result(
            db, session, user.id, "register_expense", result
        )
        assert offer is None
    finally:
        _cleanup(db, user.id)
        db.close()


def test_offer_skips_recurring_and_installment_results():
    db = SessionLocal()
    try:
        offer = offer_description_preference_from_result(
            db,
            {},
            1,
            "register_expense",
            {"id": 1, "description": "x", "type": "expense", "recurrence_id": 5},
        )
        assert offer is None
        offer = offer_description_preference_from_result(
            db,
            {},
            1,
            "register_expense",
            {"id": 1, "description": "x", "type": "expense", "installment_plan_id": 5},
        )
        assert offer is None
        offer = offer_description_preference_from_result(
            db, {}, 1, "list_transactions", {"id": 1, "description": "x", "type": "expense"}
        )
        assert offer is None
    finally:
        db.close()
