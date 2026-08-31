from app.agent.tool_parse import parse_tool_call, unsupported_tool_call
from app.schemas import ToolCall


def test_unknown_tool_becomes_unsupported():
    result = parse_tool_call({"tool": "transfer_money", "arguments": {}})
    assert result is not None
    assert result.tool == "unsupported_action"
    assert "transfer_money" in result.arguments["reason"]
    assert "não está disponível" in result.arguments["reason"]


def test_unsupported_action_with_reason():
    result = parse_tool_call(
        {
            "tool": "unsupported_action",
            "arguments": {
                "reason": "Ainda não consigo exportar relatórios em PDF.",
            },
        }
    )
    assert result == ToolCall(
        tool="unsupported_action",
        arguments={"reason": "Ainda não consigo exportar relatórios em PDF."},
    )


def test_unsupported_tool_call_default_message():
    result = unsupported_tool_call()
    assert result.tool == "unsupported_action"
    assert "ainda não está disponível" in result.arguments["reason"]
