from app.services.card_wizard import (
    begin_card_wizard,
    get_wizard,
    process_wizard_message,
    try_process_card_wizard,
)
from app.services.intents import wants_card_creation
from app.services.tools import try_rule_based_parse


def test_wants_card_creation():
    assert wants_card_creation("cadastrar cartão Nubank")
    assert wants_card_creation("criar um novo cartao")
    assert not wants_card_creation("cadastrar conta Nubank")


def test_rule_based_create_card():
    tool = try_rule_based_parse("cadastrar cartão Nubank")
    assert tool is not None
    assert tool.tool == "create_card"


def test_card_wizard_starts_on_create_card():
    session = {}
    result = begin_card_wizard(session, "cadastrar cartão")
    assert result is not None
    assert session.get("card_wizard") is not None
    assert "apelido" in result.message.lower() or "cartão" in result.message.lower()


def test_card_wizard_escapes_on_list_accounts():
    session = {}
    begin_card_wizard(session, "cadastrar cartão")
    result = process_wizard_message(session, "Liste minhas contas bancárias")
    assert result is None
    assert session.get("card_wizard") is None


def test_card_wizard_full_flow():
    session = {}
    begin_card_wizard(session, "cadastrar cartão")
    process_wizard_message(session, "Nubank")
    process_wizard_message(session, "pular")
    process_wizard_message(session, "10")
    process_wizard_message(session, "17")
    process_wizard_message(session, "pular")
    result = process_wizard_message(session, "Corrente")
    assert result is not None
    assert result.needs_confirmation
    assert result.pending_action["tool"] == "create_card"
    assert result.pending_action["arguments"]["name"] == "Nubank"
    assert result.pending_action["arguments"]["closing_day"] == 10
    assert result.pending_action["arguments"]["due_day"] == 17
    assert result.pending_action["arguments"]["settlement_account_name"] == "Corrente"


def test_try_process_restarts_on_new_card_request():
    session = {}
    begin_card_wizard(session, "cadastrar cartão")
    restarted = try_process_card_wizard(session, "cadastrar cartão Itaú")
    assert restarted is not None
    assert get_wizard(session) is not None


def test_card_wizard_ignores_empty_llm_days():
    session = {}
    result = begin_card_wizard(
        session,
        "cadastrar cartão Nubank",
        initial={
            "name": "Nubank",
            "closing_day": "",
            "due_day": "",
            "settlement_account_name": "",
        },
    )
    assert result is not None
    assert "fechamento" in result.message.lower()
    wizard = get_wizard(session)
    assert wizard is not None
    assert wizard.get("closing_day") is None
    assert wizard.get("due_day") is None


def test_card_wizard_chip_closing_day_keeps_wizard():
    session = {}
    begin_card_wizard(session, "cadastrar cartão")
    process_wizard_message(session, "Nubank")
    process_wizard_message(session, "pular")
    result = process_wizard_message(session, "10")
    assert result is not None
    assert session.get("card_wizard") is not None
    assert get_wizard(session)["closing_day"] == 10
    assert "vencimento" in result.message.lower()
