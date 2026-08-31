from app.schemas import ToolCall
from app.services.tools import correct_tool_call_descriptions, format_pending_confirmation


def test_confirmation_shows_corrected_description():
    tool_call = ToolCall(
        tool="register_expense",
        arguments={
            "amount": "40,50",
            "description": "passagens para cidade de Timbauba",
            "account_name": "Mercado Pago",
            "category_name": "Transporte",
            "transaction_date": "2026-08-29",
        },
    )
    corrected = correct_tool_call_descriptions(tool_call)
    message = format_pending_confirmation(corrected)

    assert corrected.arguments["description"] == "Passagens para cidade de Timbaúba"
    assert "Timbaúba" in message
    assert "Timbauba" not in message
