from app.schemas import ToolCall
from app.services.tools import try_rule_based_parse


def test_delete_with_amount_uses_delete_transaction():
    tool = try_rule_based_parse("Excluir o lançamento de 40,50")
    assert tool is not None
    assert tool.tool == "delete_transaction"
    assert tool.arguments.get("amount") == "40.50"


def test_delete_passagem_uses_delete_transaction():
    tool = try_rule_based_parse(
        "Exclua o lançamento da passagem de valor 40,50"
    )
    assert tool is not None
    assert tool.tool == "delete_transaction"
    assert tool.arguments.get("amount") == "40.50"
    assert tool.arguments.get("description") == "passagem"


def test_vague_delete_uses_delete_transaction():
    tool = try_rule_based_parse("Exclua um lançamento")
    assert tool is not None
    assert tool.tool == "delete_transaction"
