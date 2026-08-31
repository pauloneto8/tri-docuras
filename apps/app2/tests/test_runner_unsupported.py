from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.runner import process_message
from app.schemas import ToolCall


@pytest.mark.asyncio
async def test_runner_returns_unsupported_action_message():
    session = {}
    db = MagicMock()
    tool = ToolCall(
        tool="unsupported_action",
        arguments={
            "reason": "Ainda não consigo exportar relatórios em PDF.",
        },
    )

    with patch(
        "app.agent.runner.call_intent_llm",
        new_callable=AsyncMock,
        return_value=(tool, "groq"),
    ):
        result = await process_message(
            db, 1, "Exportar relatório em PDF", session=session
        )

    assert result.tool_used == "unsupported_action"
    assert "exportar" in result.message.lower() or "pdf" in result.message.lower()
    assert result.needs_confirmation is False
