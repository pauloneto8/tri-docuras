import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agent.runner import process_message
from app.auth import create_user
from app.models import Account, Category, Transaction, User
from app.schemas import CreateAccountInput, RegisterExpenseInput
from app.services import finance


@pytest.mark.asyncio
async def test_realize_planned_wizard_asks_same_account_then_other_account():
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"rwiz_{suffix}@test.com",
        password="secret1",
        name="Wizard User",
        is_active=True,
    )
    session: dict = {}
    try:
        finance.seed_defaults(db, user.id)
        account_a = finance.create_account(
            db,
            user.id,
            CreateAccountInput(name=f"Carteira_{suffix}", account_type="carteira"),
        )
        account_b = finance.create_account(
            db,
            user.id,
            CreateAccountInput(name=f"Nubank_{suffix}", account_type="corrente"),
        )
        planned = finance.register_expense(
            db,
            user.id,
            RegisterExpenseInput(
                amount="90",
                description="Aluguel previsto",
                account_name=account_a["name"],
                category_name="Moradia",
                status="planned",
            ),
        )

        with patch("app.agent.runner.call_intent_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = (None, "groq")
            r1 = await process_message(db, user.id, "realizar previsão do aluguel", session=session)

        assert "conta" in r1.message.lower() or "pagamento" in r1.message.lower()

        with patch("app.agent.runner.call_intent_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = (None, "groq")
            r2 = await process_message(db, user.id, "hoje", session=session)

        assert "mesma conta" in r2.message.lower()

        with patch("app.agent.runner.call_intent_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = (None, "groq")
            r3 = await process_message(db, user.id, "Outra conta", session=session)

        assert "qual conta" in r3.message.lower()

        with patch("app.agent.runner.call_intent_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = (None, "groq")
            r4 = await process_message(db, user.id, account_b["name"], session=session)

        assert r4.needs_confirmation
        assert r4.pending_action["arguments"]["account_name"] == account_b["name"]
        assert r4.pending_action["arguments"]["planned_id"] == planned["id"]
    finally:
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()
