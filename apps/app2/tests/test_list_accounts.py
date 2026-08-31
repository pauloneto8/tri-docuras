from app.services.account_wizard import begin_account_wizard, process_wizard_message
from app.services.tools import execute_tool, format_tool_result, try_rule_based_parse
from app.schemas import ToolCall


def test_rule_based_list_accounts():
    tool = try_rule_based_parse("Liste minhas contas bancárias")
    assert tool is not None
    assert tool.tool == "list_accounts"


def test_account_wizard_escapes_on_list_request():
    session = {}
    begin_account_wizard(session, "cadastrar conta")
    result = process_wizard_message(session, "Liste minhas contas bancárias")
    assert result is None
    assert session.get("account_wizard") is None


def test_account_wizard_keeps_on_valid_type():
    session = {}
    begin_account_wizard(session, "cadastrar conta")
    process_wizard_message(session, "Nubank")
    result = process_wizard_message(session, "corrente")
    assert result is not None
    assert "instituição" in result.message.lower() or "instituicao" in result.message.lower()
