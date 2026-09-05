"""Retomada do lançamento após criar categoria no meio do wizard."""

import uuid
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import create_user
from app.models import Account, Category, Transaction, User
from app.schemas import CreateAccountInput
from app.services import finance
from app.services.category_wizard import get_wizard as get_category_wizard
from app.services.transaction_slots import WIZARD_KEY
from app.services.transaction_wizard import (
    get_paused_wizard,
    get_wizard,
    try_process_transaction_wizard,
)


def _setup(db, user):
    finance.seed_defaults(db, user.id)
    finance.create_account(
        db,
        user.id,
        CreateAccountInput(
            name="Flash",
            account_type="corrente",
            opening_balance="100",
            opening_balance_date=date(2026, 1, 1),
        ),
    )


def _almost_complete_income_wizard() -> dict:
    return {
        "tx_type": "income",
        "status": "planned",
        "amount": "594",
        "description": "Vale e Auxílio",
        "account_name": "Flash",
        "card_name": None,
        "category_name": None,
        "competence_date": "2026-09-01",
        "due_date": "2026-09-01",
        "payment_date": None,
        "transaction_date": "2026-09-01",
        "payment_source": "account",
        "payment_on_card": False,
        "has_credit_cards": False,
        "payment_mode": "installment",
        "is_recurring": False,
        "frequency": None,
        "recurrence_end_date": None,
        "recurrence_end_asked": False,
        "installment_count": 12,
        "installment_interval": "monthly",
        "installment_start_index": 8,
        "installment_amount_basis": "installment",
        "source_message": "Lance uma receita de 594",
        "suggested_category": None,
    }


@pytest.mark.asyncio
async def test_new_category_pauses_transaction_wizard():
    from app.config import settings

    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"resume_cat_{suffix}@test.com",
        password="secret1",
        name="Resume Cat",
        is_active=True,
    )
    try:
        _setup(db, user)
        session = {WIZARD_KEY: _almost_complete_income_wizard()}

        result = try_process_transaction_wizard(
            session, "Vale e Auxílio", db=db, user_id=user.id
        )
        assert result is not None
        assert get_wizard(session) is None
        paused = get_paused_wizard(session)
        assert paused is not None
        assert paused["amount"] == "594"
        assert get_category_wizard(session) is not None
        assert result.needs_confirmation
        assert result.pending_action["tool"] == "create_category"
        assert result.pending_action["arguments"]["type"] == "income"
        assert "vale" in result.pending_action["arguments"]["name"].lower()
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(
            synchronize_session=False
        )
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_resume_after_create_category_confirms_income():
    from app.config import settings
    from app.schemas import ToolCall
    from app.services.category_wizard import clear_wizard as clear_category_wizard
    from app.services.tools import execute_tool
    from app.services.transaction_wizard import (
        PAUSED_WIZARD_KEY,
        resume_paused_transaction_after_category,
    )

    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"resume_run_{suffix}@test.com",
        password="secret1",
        name="Resume Run",
        is_active=True,
    )
    try:
        _setup(db, user)
        session = {PAUSED_WIZARD_KEY: _almost_complete_income_wizard()}
        outcome = execute_tool(
            db,
            user.id,
            ToolCall(
                tool="create_category",
                arguments={"name": f"Vale e Auxílio {suffix}", "type": "income"},
            ),
        )
        clear_category_wizard(session)
        resumed = resume_paused_transaction_after_category(
            session, category_name=outcome["result"]["name"]
        )
        assert resumed is not None
        assert resumed.needs_confirmation
        assert resumed.pending_action["tool"] == "register_income"
        assert resumed.pending_action["arguments"]["amount"] == "594"
        assert resumed.pending_action["arguments"]["category_name"] == outcome["result"]["name"]
        assert get_wizard(session) is not None
        assert get_paused_wizard(session) is None
        assert "categoria" in resumed.message.lower()
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(
            synchronize_session=False
        )
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()
