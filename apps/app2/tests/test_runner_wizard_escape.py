from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.runner import process_message
from app.schemas import ToolCall
from app.services.account_wizard import begin_account_wizard, get_wizard as get_account_wizard
from app.services.transaction_wizard import begin_login_prompt, get_wizard


@pytest.mark.asyncio
async def test_runner_escapes_tx_wizard_and_calls_llm():
    session = {}
    begin_login_prompt(session)
    assert get_wizard(session) is not None

    tool = ToolCall(tool="get_summary", arguments={})
    db = MagicMock()

    with patch(
        "app.agent.runner.call_intent_llm",
        new_callable=AsyncMock,
        return_value=(tool, "groq"),
    ):
        with patch(
            "app.agent.runner.execute_tool",
            return_value={"action": "get_summary", "result": {}},
        ):
            with patch(
                "app.agent.runner.format_tool_result",
                return_value="Resumo pronto.",
            ):
                result = await process_message(db, 1, "resumo do mês", session=session)

    assert get_wizard(session) is None
    assert result.source == "groq"
    assert "Resumo" in result.message


@pytest.mark.asyncio
async def test_runner_escapes_tx_wizard_for_account_creation():
    session = {}
    begin_login_prompt(session)

    tool = ToolCall(
        tool="create_account",
        arguments={"name": "", "account_type": "corrente"},
    )
    db = MagicMock()

    with patch(
        "app.agent.runner.call_intent_llm",
        new_callable=AsyncMock,
        return_value=(tool, "groq"),
    ):
        result = await process_message(
            db, 1, "Cadastrar uma nova conta bancária", session=session
        )

    assert get_wizard(session) is None
    assert get_account_wizard(session) is not None
    assert "apelido" in result.message.lower()


@pytest.mark.asyncio
async def test_runner_lists_accounts_from_account_wizard():
    session = {}
    begin_account_wizard(session, "cadastrar conta")
    assert get_account_wizard(session) is not None

    tool = ToolCall(tool="list_accounts", arguments={})
    db = MagicMock()
    with patch(
        "app.agent.runner.call_intent_llm",
        new_callable=AsyncMock,
        return_value=(tool, "groq"),
    ):
        with patch(
            "app.agent.runner.execute_tool",
            return_value={
                "action": "list_accounts",
                "result": [
                    {
                        "account": "Nubank",
                        "account_type_label": "Corrente",
                        "institution": "Nubank",
                        "balance": "100,00",
                    }
                ],
            },
        ):
            result = await process_message(
                db, 1, "Liste minhas contas bancárias", session=session
            )

    assert get_account_wizard(session) is None
    assert result.tool_used == "list_accounts"
    assert "Nubank" in result.message


@pytest.mark.asyncio
async def test_runner_quais_conta_not_start_wizard():
    session = {}
    db = MagicMock()
    tool = ToolCall(tool="list_accounts", arguments={})

    with patch(
        "app.agent.runner.call_intent_llm",
        new_callable=AsyncMock,
        return_value=(tool, "groq"),
    ):
        with patch(
            "app.agent.runner.execute_tool",
            return_value={"action": "list_accounts", "result": []},
        ):
            result = await process_message(db, 1, "Quais a conta bancária?", session=session)

    assert get_account_wizard(session) is None
    assert result.tool_used == "list_accounts"
    assert "Nenhuma conta" in result.message
