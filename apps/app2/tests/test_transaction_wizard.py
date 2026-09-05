import pytest

from app.services.transaction_wizard import (
    begin_login_prompt,
    clear_wizard,
    get_wizard,
    start_wizard,
    try_process_transaction_wizard,
)
from app.timezone import local_today
from tests.wizard_helpers import decline_recurring


def test_login_prompt_starts_wizard():
    session = {}
    result = begin_login_prompt(session)
    assert "despesa" in result.message.lower()
    assert get_wizard(session) is not None


def test_parses_short_expense_answer_asks_status():
    session = {}
    start_wizard(session)
    result = try_process_transaction_wizard(session, "despesa")
    assert result is not None
    assert "realizado" in result.message.lower() or "previsto" in result.message.lower()
    assert get_wizard(session)["status"] is None


def test_status_then_asks_payment_mode_for_actual():
    session = {}
    start_wizard(session)
    try_process_transaction_wizard(session, "despesa")
    result = try_process_transaction_wizard(session, "realizado")
    assert result is not None
    assert (
        "único" in result.message.lower()
        or "unico" in result.message.lower()
        or "parcelado" in result.message.lower()
        or "fixo" in result.message.lower()
    )
    assert get_wizard(session)["status"] == "actual"


def test_actual_realization_date_fills_competence_and_due():
    session = {}
    start_wizard(session)
    try_process_transaction_wizard(session, "despesa")
    try_process_transaction_wizard(session, "realizado")
    decline_recurring(session)
    try_process_transaction_wizard(session, "hoje")
    wizard = get_wizard(session)
    from app.services.transaction_wizard import _next_field

    assert _next_field(wizard) == "amount"
    today = local_today().isoformat()
    assert wizard["payment_date"] == today
    assert wizard["competence_date"] == today
    assert wizard["due_date"] == today


def test_escapes_wizard_for_account_creation():
    session = {}
    start_wizard(session)
    result = try_process_transaction_wizard(session, "Cadastrar uma nova conta bancária")
    assert result is None
    assert get_wizard(session) is None


def test_escapes_wizard_when_user_rejects_tx_and_wants_account():
    session = {}
    start_wizard(session)
    message = "Não quero lançar despesa ou receita quero cadastro uma nova conta bancária"
    result = try_process_transaction_wizard(session, message)
    assert result is None
    assert get_wizard(session) is None


def test_keeps_wizard_on_invalid_amount():
    session = {}
    start_wizard(session)
    try_process_transaction_wizard(session, "despesa")
    try_process_transaction_wizard(session, "realizado")
    decline_recurring(session)
    try_process_transaction_wizard(session, "hoje")
    result = try_process_transaction_wizard(session, "abc")
    assert result is None
    assert get_wizard(session) is None


def test_cancel_clears_wizard():
    session = {}
    start_wizard(session)
    result = try_process_transaction_wizard(session, "cancelar")
    assert result is not None
    assert "cancelado" in result.message.lower()
    assert get_wizard(session) is None


def test_nao_on_recurring_slot_does_not_cancel():
    session = {}
    start_wizard(session)
    try_process_transaction_wizard(session, "despesa")
    try_process_transaction_wizard(session, "realizado")
    try_process_transaction_wizard(session, "Não")
    result = try_process_transaction_wizard(session, "hoje")
    assert result is not None
    assert get_wizard(session) is not None
    from app.services.transaction_wizard import _next_field

    assert _next_field(get_wizard(session)) == "amount"


def test_wizard_accepts_ontem_during_account_step():
    from datetime import timedelta

    session = {}
    start_wizard(session)
    try_process_transaction_wizard(session, "despesa")
    try_process_transaction_wizard(session, "realizado")
    decline_recurring(session)
    try_process_transaction_wizard(session, "hoje")
    try_process_transaction_wizard(session, "50")
    try_process_transaction_wizard(session, "mercado")

    result = try_process_transaction_wizard(session, "foi ontem")
    assert result is not None
    assert "ontem" in result.message.lower() or "anotada" in result.message.lower()
    wizard = get_wizard(session)
    assert wizard is not None
    assert wizard["transaction_date"] == (local_today() - timedelta(days=1)).isoformat()
    assert wizard["description"] == "Mercado"
    assert wizard["status"] == "actual"


def test_planned_asks_competence_then_due():
    session = {}
    start_wizard(session)
    try_process_transaction_wizard(session, "despesa")
    result = try_process_transaction_wizard(session, "previsto")
    assert result is not None
    assert "competência" in result.message.lower() or "competencia" in result.message.lower()

    result = try_process_transaction_wizard(session, "agosto")
    assert result is not None
    assert "vencimento" in result.message.lower()
    wizard = get_wizard(session)
    assert wizard["competence_date"] == f"{local_today().year}-08-01"
    assert wizard["due_date"] is None

    result = try_process_transaction_wizard(session, "10/08/2026")
    assert result is not None
    assert "fixo" in result.message.lower() or "recorr" in result.message.lower()
    decline_recurring(session)
    result = try_process_transaction_wizard(session, "50")
    assert result is not None
    assert "conta" in result.message.lower() or "descrição" in result.message.lower() or get_wizard(session).get("amount")
    wizard = get_wizard(session)
    assert wizard["competence_date"] == f"{local_today().year}-08-01"
    assert wizard["due_date"] == "2026-08-10"
    assert wizard["payment_date"] is None
    assert wizard["status"] == "planned"


def test_description_mercado_ontem_sets_yesterday():
    from datetime import timedelta

    session = {}
    start_wizard(session)
    try_process_transaction_wizard(session, "despesa")
    try_process_transaction_wizard(session, "previsto")
    try_process_transaction_wizard(session, "hoje")
    try_process_transaction_wizard(session, "também")
    try_process_transaction_wizard(session, "único")
    try_process_transaction_wizard(session, "50")
    result = try_process_transaction_wizard(session, "mercado ontem")
    assert result is not None
    wizard = get_wizard(session)
    assert wizard["description"] == "Mercado"
    assert wizard["transaction_date"] == (local_today() - timedelta(days=1)).isoformat()
    assert wizard["status"] == "planned"


@pytest.mark.asyncio
async def test_login_wizard_asks_payment_source_when_user_has_card():
    import uuid

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.auth import create_user
    from app.config import settings
    from app.models import Account, CardInvoice, Category, CreditCard, User
    from app.schemas import CreateCardInput
    from app.services import finance
    from tests.test_transaction_slots import _create_account, _setup_user

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"login_wiz_{suffix}@test.com",
        password="secret1",
        name="Login Wizard",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        account_name = f"Mercado Pago_{suffix}"
        _create_account(db, user.id, account_name)
        finance.create_card(
            db,
            user.id,
            CreateCardInput(
                name=f"Cartão_{suffix}",
                closing_day=9,
                due_day=14,
                settlement_account_name=account_name,
            ),
        )
        session = {}
        begin_login_prompt(session)
        result = try_process_transaction_wizard(session, "despesa", db=db, user_id=user.id)
        assert result is not None
        assert "cartão" in result.message.lower()
        assert "conta" in result.message.lower()
    finally:
        db.query(CardInvoice).filter(CardInvoice.user_id == user.id).delete(synchronize_session=False)
        db.query(CreditCard).filter(CreditCard.user_id == user.id).delete(synchronize_session=False)
        db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()
