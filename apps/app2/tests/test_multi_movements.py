from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.runner import process_message
from app.services.multi_movement_flow import execute_batch_movements
from app.services.multi_movements import parse_multi_movements
from app.services.transaction_wizard import begin_login_prompt, get_wizard, start_wizard


def test_parse_real_passagens_recarga():
    message = (
        "Ontem tive as despesas de 54 de passagens para o trabalho. "
        "E também 30,00 de recarga de celular."
    )
    items = parse_multi_movements(message)
    assert items is not None
    assert len(items) == 2
    assert items[0].amount == "54"
    assert "passagens" in items[0].description.lower()
    assert items[1].amount in {"30", "30.00"}
    assert "recarga" in items[1].description.lower()
    assert "30" not in items[0].description
    assert items[0].tx_type == "expense"
    assert items[0].transaction_date == (date.today() - timedelta(days=1)).isoformat()


def test_parse_passagem_e_recarga_sem_virgula():
    message = "gastei 54 de passagem e 30 de recarga"
    items = parse_multi_movements(message)
    assert items is not None
    assert len(items) == 2
    assert items[0].amount == "54"
    assert items[1].amount == "30"
    assert "passagem" in items[0].description.lower()
    assert "recarga" in items[1].description.lower()
    assert "30" not in items[0].description
    assert "54" not in items[1].description


def test_parse_two_amounts_with_wizard_hint():
    message = "54 e 30"
    assert parse_multi_movements(message) is None
    items = parse_multi_movements(message, tx_type_hint="expense")
    assert items is not None
    assert len(items) == 2
    assert items[0].amount == "54"
    assert items[1].amount == "30"


def test_parse_three_expenses():
    message = "gastei 54 de passagem, 30 de recarga e 12 de café"
    items = parse_multi_movements(message)
    assert items is not None
    assert len(items) == 3
    amounts = {item.amount for item in items}
    assert "54" in amounts
    assert "30" in amounts
    assert "12" in amounts


def test_single_expense_not_multi():
    message = "gastei 45,90 no mercado ontem"
    assert parse_multi_movements(message) is None


@pytest.mark.asyncio
async def test_runner_multi_skips_llm():
    session = {}
    db = MagicMock()
    message = (
        "Ontem tive as despesas de 54 de passagens para o trabalho. "
        "E também 30,00 de recarga de celular."
    )

    with patch("app.agent.runner.call_intent_llm", new_callable=AsyncMock) as mock_llm:
        with patch(
            "app.services.multi_movement_flow.infer_account_name",
            return_value="Carteira",
        ):
            with patch(
                "app.services.multi_movement_flow.infer_category_name",
                side_effect=["Transporte", "Outros"],
            ):
                result = await process_message(db, 1, message, session=session)

    mock_llm.assert_not_called()
    assert result.source == "multi"
    assert result.needs_confirmation is True
    assert result.pending_action is not None
    assert result.pending_action.get("batch") is True
    assert len(result.pending_action["items"]) == 2


@pytest.mark.asyncio
async def test_runner_wizard_active_two_amounts():
    session = {}
    begin_login_prompt(session)
    try_process = __import__(
        "app.services.transaction_wizard", fromlist=["try_process_transaction_wizard"]
    ).try_process_transaction_wizard
    try_process(session, "despesa")
    assert get_wizard(session)["tx_type"] == "expense"

    db = MagicMock()
    message = "54 e 30"

    with patch("app.agent.runner.call_intent_llm", new_callable=AsyncMock) as mock_llm:
        with patch(
            "app.services.multi_movement_flow.infer_account_name",
            return_value="Carteira",
        ):
            with patch(
                "app.services.multi_movement_flow.infer_category_name",
                return_value="Outros",
            ):
                result = await process_message(db, 1, message, session=session)

    mock_llm.assert_not_called()
    assert result.source == "multi"
    assert result.needs_confirmation is True
    assert len(result.pending_action["items"]) == 2
    assert get_wizard(session) is None


def test_execute_batch_movements():
    db = MagicMock()
    batch = {
        "batch": True,
        "items": [
            {
                "tool": "register_expense",
                "arguments": {
                    "amount": "54",
                    "description": "Passagens",
                    "account_name": "Carteira",
                    "category_name": "Transporte",
                    "transaction_date": date.today().isoformat(),
                },
            },
            {
                "tool": "register_expense",
                "arguments": {
                    "amount": "30",
                    "description": "Recarga",
                    "account_name": "Carteira",
                    "category_name": "Outros",
                    "transaction_date": date.today().isoformat(),
                },
            },
        ],
    }
    with patch(
        "app.services.multi_movement_flow.finance.register_expense",
        side_effect=[
            {
                "amount": "54",
                "description": "Passagens",
                "category": "Transporte",
                "transaction_date": date.today().isoformat(),
            },
            {
                "amount": "30",
                "description": "Recarga",
                "category": "Outros",
                "transaction_date": date.today().isoformat(),
            },
        ],
    ):
        msg = execute_batch_movements(db, 1, batch)
    assert "2 lançamentos registrados" in msg
    assert "Passagens" in msg
    assert "Recarga" in msg
