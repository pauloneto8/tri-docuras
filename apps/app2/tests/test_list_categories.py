from app.services.category_wizard import begin_category_wizard, process_wizard_message
from app.services.tools import execute_tool, format_tool_result, try_rule_based_parse
from app.schemas import ToolCall


def test_rule_based_list_categories():
    tool = try_rule_based_parse("Liste minhas categorias")
    assert tool is not None
    assert tool.tool == "list_categories"


def test_category_wizard_escapes_on_list_request():
    session = {}
    begin_category_wizard(session, "cadastrar categoria")
    result = process_wizard_message(session, "Liste minhas categorias")
    assert result is None
    assert session.get("category_wizard") is None


def test_format_list_categories_empty():
    assert format_tool_result("list_categories", []) == "Nenhuma categoria cadastrada."


def test_format_list_categories_with_items():
    result = format_tool_result(
        "list_categories",
        [
            {"name": "Mercado", "type_label": "Despesa", "keywords": "supermercado"},
            {"name": "Salário", "type_label": "Receita"},
        ],
    )
    assert "Suas categorias:" in result
    assert "Mercado (Despesa)" in result
    assert "Salário (Receita)" in result
    assert "palavras-chave" not in result
