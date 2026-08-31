from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.runner import process_message
from app.schemas import ToolCall
from app.services.account_wizard import begin_account_wizard, get_wizard as get_account_wizard
from app.services.transaction_wizard import begin_login_prompt, get_wizard, start_wizard


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


@pytest.mark.asyncio
async def test_runner_correction_uses_update_not_register():
    session = {}
    db = MagicMock()
    message = (
        "Corrija o lançamento da despesa com passagem de 40,50. "
        "A conta corrente é o Mercado Pago"
    )
    tool = ToolCall(
        tool="update_transaction",
        arguments={
            "description": "passagem",
            "amount": "40.50",
            "account_name": "Mercado Pago",
        },
    )

    with patch(
        "app.agent.runner.call_intent_llm",
        new_callable=AsyncMock,
        return_value=(tool, "groq"),
    ) as llm:
        result = await process_message(db, 1, message, session=session)

    llm.assert_awaited_once()
    assert result.tool_used == "update_transaction"
    assert result.needs_confirmation
    assert "Mercado Pago" in result.message
    assert result.pending_action["tool"] == "update_transaction"


@pytest.mark.asyncio
async def test_runner_fix_account_not_list_accounts():
    session = {}
    db = MagicMock()
    message = "Eu pedi para corrigir a conta bancária na despesa da passagem"
    tool = ToolCall(
        tool="update_transaction",
        arguments={"description": "passagem", "account_name": "Mercado Pago"},
    )

    with patch(
        "app.agent.runner.call_intent_llm",
        new_callable=AsyncMock,
        return_value=(tool, "groq"),
    ):
        result = await process_message(db, 1, message, session=session)

    assert result.tool_used == "update_transaction"
    assert result.tool_used != "list_accounts"


@pytest.mark.asyncio
async def test_runner_register_expense_via_llm():
    session = {}
    db = MagicMock()
    message = "Hoje gastei 54 reais de passagem"
    tool = ToolCall(
        tool="register_expense",
        arguments={"amount": "54", "description": "passagem"},
    )

    from app.services.transaction_slots import SlotResult

    with patch(
        "app.agent.runner.call_intent_llm",
        new_callable=AsyncMock,
        return_value=(tool, "groq"),
    ):
        with patch(
            "app.services.transaction_slots.ensure_transaction_slots",
            return_value=SlotResult(question="Em qual conta registrar?"),
        ):
            result = await process_message(db, 1, message, session=session)

    assert "conta" in result.message.lower()


@pytest.mark.asyncio
async def test_wizard_account_name_stays_in_wizard():
    session = {}
    start_wizard(session)
    from app.services.transaction_wizard import try_process_transaction_wizard

    try_process_transaction_wizard(session, "despesa")
    try_process_transaction_wizard(session, "realizado")
    try_process_transaction_wizard(session, "hoje")
    try_process_transaction_wizard(session, "40,50")
    try_process_transaction_wizard(session, "passagem")

    db = MagicMock()
    with patch(
        "app.services.transaction_wizard.list_active_account_names",
        return_value=["Mercado Pago", "Carteira"],
    ):
        with patch(
            "app.services.transaction_wizard.parse_account_answer",
            return_value="Mercado Pago",
        ):
            with patch(
                "app.services.transaction_wizard.fill_slot",
                return_value=None,
            ):
                with patch(
                    "app.services.transaction_wizard._apply_inference",
                ):
                    with patch(
                        "app.services.transaction_wizard._question_for_slot",
                        return_value="Qual categoria?",
                    ):
                        result = try_process_transaction_wizard(
                            session, "Mercado Pago", db=db, user_id=1
                        )

    assert result is not None
    assert get_wizard(session) is not None


@pytest.mark.asyncio
async def test_wizard_escapes_on_correction_phrase():
    session = {}
    start_wizard(session)
    from app.services.transaction_wizard import try_process_transaction_wizard

    message = (
        "Corrija o lançamento da despesa com passagem de 40,50. "
        "A conta corrente é o Mercado Pago"
    )
    result = try_process_transaction_wizard(session, message, db=MagicMock(), user_id=1)

    assert result is None
    assert get_wizard(session) is None
