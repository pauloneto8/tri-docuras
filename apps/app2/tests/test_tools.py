import pytest
from datetime import date

from app.schemas import decimal_to_cents, format_brl, ToolCall
from app.services.tools import try_rule_based_parse, format_tool_result


def test_decimal_to_cents():
    assert decimal_to_cents("45,90") == 4590
    assert decimal_to_cents("1.234,56") == 123456
    assert decimal_to_cents("10") == 1000


def test_format_brl():
    assert format_brl(0) == "0,00"
    assert format_brl(4590) == "45,90"
    assert format_brl(88963) == "889,63"
    assert format_brl(123456) == "1.234,56"
    assert format_brl(-3000) == "-30,00"


def test_rule_based_expense():
    result = try_rule_based_parse("gastei 45,90 no mercado ontem")
    assert result is not None
    assert result.tool == "register_expense"
    assert result.arguments["amount"] == "45.90"
    assert "mercado" in result.arguments["description"].lower()
    from datetime import timedelta

    from app.timezone import local_today

    assert result.arguments["transaction_date"] == (
        local_today() - timedelta(days=1)
    ).isoformat()


def test_rule_based_income():
    result = try_rule_based_parse("recebi 1500 de salario")
    assert result is not None
    assert result.tool == "register_income"
    assert result.arguments["amount"] == "1500"


def test_rule_based_summary():
    result = try_rule_based_parse("resumo do mes")
    assert result is not None
    assert result.tool == "get_summary"


def test_rule_based_list():
    result = try_rule_based_parse("ultimas despesas")
    assert result is not None
    assert result.tool == "list_transactions"
    assert result.arguments["type"] == "expense"


def test_rule_based_expense_transport():
    result = try_rule_based_parse("Hoje gastei r$ 60 com transporte")
    assert result is not None
    assert result.arguments["description"] == "transporte"


def test_rule_based_expense_moto():
    result = try_rule_based_parse("Hoje eu gastei r$ 12 com viagem de moto")
    assert result is not None
    assert result.arguments["description"] == "viagem de moto"


def test_format_register_expense():
    msg = format_tool_result(
        "register_expense",
        {
            "amount": "45.90",
            "description": "mercado",
            "category": "Alimentação",
            "transaction_date": date.today().isoformat(),
        },
    )
    assert "Despesa de R$" in msg
    assert "45.90" in msg
