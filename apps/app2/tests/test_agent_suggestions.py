from app.services.agent_suggestions import (
    for_account_wizard_field,
    for_category_wizard_field,
    for_transaction_wizard_field,
)


def test_transaction_type_suggestions():
    chips = for_transaction_wizard_field("tx_type", None, None, {})
    assert "Despesa" in chips
    assert "Receita" in chips
    assert "Cancelar" in chips


def test_account_type_suggestions():
    chips = for_account_wizard_field("account_type")
    assert "Corrente" in chips
    assert "Poupança" in chips
    assert "Cancelar" in chips


def test_category_type_suggestions():
    chips = for_category_wizard_field("category_type")
    assert "Despesa" in chips
    assert "Receita" in chips


def test_transaction_date_suggestions():
    chips = for_transaction_wizard_field("payment_date", None, None, {})
    assert "Hoje" in chips
    assert "Ontem" in chips
    chips_due = for_transaction_wizard_field("due_date", None, None, {})
    assert "Amanhã" in chips_due
