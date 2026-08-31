from app.services.transaction_wizard import (
    begin_login_prompt,
    clear_wizard,
    get_wizard,
    start_wizard,
    try_process_transaction_wizard,
)
from app.timezone import local_today


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


def test_status_then_asks_realization_date():
    session = {}
    start_wizard(session)
    try_process_transaction_wizard(session, "despesa")
    result = try_process_transaction_wizard(session, "realizado")
    assert result is not None
    assert "realização" in result.message.lower() or "realizacao" in result.message.lower()
    assert get_wizard(session)["status"] == "actual"


def test_actual_realization_date_fills_competence_and_due():
    session = {}
    start_wizard(session)
    try_process_transaction_wizard(session, "despesa")
    try_process_transaction_wizard(session, "realizado")
    result = try_process_transaction_wizard(session, "hoje")
    assert result is not None
    assert "valor" in result.message.lower()
    wizard = get_wizard(session)
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


def test_wizard_accepts_ontem_during_account_step():
    from datetime import timedelta

    session = {}
    start_wizard(session)
    try_process_transaction_wizard(session, "despesa")
    try_process_transaction_wizard(session, "realizado")
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
    assert "valor" in result.message.lower()
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
    try_process_transaction_wizard(session, "amanhã")
    try_process_transaction_wizard(session, "50")
    result = try_process_transaction_wizard(session, "mercado ontem")
    assert result is not None
    wizard = get_wizard(session)
    assert wizard["description"] == "Mercado"
    assert wizard["transaction_date"] == (local_today() - timedelta(days=1)).isoformat()
    assert wizard["status"] == "planned"
