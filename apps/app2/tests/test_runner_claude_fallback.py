from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.runner import process_message
from app.schemas import ToolCall


@pytest.mark.asyncio
async def test_runner_falls_back_to_claude_when_groq_and_rule_fail():
    session = {}
    db = MagicMock()
    tool = ToolCall(tool="get_summary", arguments={})

    with (
        patch(
            "app.agent.runner.call_intent_llm",
            new_callable=AsyncMock,
            return_value=(None, "groq"),
        ),
        patch("app.agent.runner.try_rule_based_parse", return_value=None),
        patch(
            "app.agent.runner.call_claude_intent_llm",
            new_callable=AsyncMock,
            return_value=(tool, "claude-fallback"),
        ) as claude_fallback,
        patch(
            "app.agent.runner.execute_tool",
            return_value={"action": "get_summary", "result": {}},
        ),
        patch("app.agent.runner.format_tool_result", return_value="Resumo pronto."),
    ):
        result = await process_message(
            db, 1, "me fala como anda minha grana esse mes", session=session
        )

    claude_fallback.assert_awaited_once()
    assert result.source == "claude-fallback"
    assert "Resumo" in result.message


@pytest.mark.asyncio
async def test_runner_gives_up_when_claude_fallback_also_fails():
    session = {}
    db = MagicMock()

    with (
        patch(
            "app.agent.runner.call_intent_llm",
            new_callable=AsyncMock,
            return_value=(None, "groq"),
        ),
        patch("app.agent.runner.try_rule_based_parse", return_value=None),
        patch(
            "app.agent.runner.call_claude_intent_llm",
            new_callable=AsyncMock,
            return_value=(None, "claude-fallback"),
        ),
    ):
        result = await process_message(
            db, 1, "me fala algo que nenhuma regra reconhece", session=session
        )

    assert result.tool_used is None
    assert "não consegui entender" in result.message.lower()
