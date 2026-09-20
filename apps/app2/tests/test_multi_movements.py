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


def test_date_only_not_multi():
    assert parse_multi_movements("10/08/2026") is None
    assert parse_multi_movements("03/09/2026") is None
    assert parse_multi_movements("31-08-2026") is None


def test_mixed_expense_income_split():
    message = "gastei 50 no mercado e recebi 30 de reembolso"
    items = parse_multi_movements(message)
    assert items is not None
    assert len(items) == 2
    assert items[0].amount == "50"
    assert items[0].tx_type == "expense"
    assert "mercado" in items[0].description.lower()
    assert items[1].amount == "30"
    assert items[1].tx_type == "income"
    assert "reembolso" in items[1].description.lower()


def test_mixed_income_expense_split_reversed():
    message = "recebi 30 de reembolso e gastei 50 no mercado"
    items = parse_multi_movements(message)
    assert items is not None
    assert len(items) == 2
    assert items[0].amount == "30"
    assert items[0].tx_type == "income"
    assert items[1].amount == "50"
    assert items[1].tx_type == "expense"


def test_dedup_same_amount_different_description_both_kept():
    message = "gastei 50 no mercado e 50 na farmácia"
    items = parse_multi_movements(message)
    assert items is not None
    assert len(items) == 2
    assert {item.amount for item in items} == {"50"}
    descriptions = {item.description.lower() for item in items}
    assert any("mercado" in d for d in descriptions)
    assert any("farm" in d for d in descriptions)


def test_dedup_true_duplicate_still_collapses():
    # Mesma cláusula repetida por engano gera 2 valores com a mesma descrição
    # (após limpeza) — isso ainda deve colapsar para 1 lançamento.
    message = "gastei 50 de mercado e 50 de mercado"
    items = parse_multi_movements(message)
    assert items is None  # menos de 2 itens após dedup, comportamento já existente


def test_mixed_type_comma_clause_falls_back_to_default():
    # Limitação documentada: cláusulas só são separadas por "." ou " e " —
    # vírgula não separa cláusula para fins de tipo por item, então cai no
    # default da mensagem inteira (despesa, por ter pista de despesa também).
    message = "gastei 50 no mercado, recebi 30 de reembolso"
    items = parse_multi_movements(message)
    assert items is not None
    assert len(items) == 2
    assert items[0].tx_type == "expense"
    assert items[1].tx_type == "expense"


@pytest.mark.asyncio
async def test_runner_due_date_does_not_spawn_multi_expenses():
    session = {}
    begin_login_prompt(session)
    from app.services.transaction_wizard import try_process_transaction_wizard

    try_process_transaction_wizard(session, "despesa")
    try_process_transaction_wizard(session, "previsto")
    try_process_transaction_wizard(session, "agosto")
    assert get_wizard(session) is not None

    db = MagicMock()
    with patch("app.agent.runner.call_intent_llm", new_callable=AsyncMock) as mock_llm:
        result = await process_message(db, 1, "10/08/2026", session=session)

    mock_llm.assert_not_called()
    assert result.source == "wizard"
    if "fixo" in result.message.lower() or "recorr" in result.message.lower():
        result = await process_message(db, 1, "Não", session=session)
    assert "valor" in result.message.lower()
    assert get_wizard(session)["due_date"] == "2026-08-10"
    assert "pending_movements" not in session or session.get("pending_movements") is None


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
