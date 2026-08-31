from app.schemas import ToolCall
from app.services.tools import try_rule_based_parse


def test_correction_fallback_uses_update_transaction():
    tool = try_rule_based_parse(
        "Corrija o lançamento da despesa com passagem de 40,50. "
        "A conta corrente é o Mercado Pago"
    )
    assert tool is not None
    assert tool.tool == "update_transaction"
    assert tool.arguments.get("amount") == "40.50"
    assert tool.arguments.get("account_name") == "Mercado Pago"


def test_correction_without_amount_returns_none():
    tool = try_rule_based_parse("Eu pedi para corrigir a conta bancária na despesa da passagem")
    assert tool is not None
    assert tool.tool == "update_transaction"
    assert tool.arguments.get("description") == "passagem"
