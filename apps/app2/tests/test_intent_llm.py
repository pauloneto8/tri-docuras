from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.agent.llm import call_intent_llm
from app.schemas import ToolCall


@pytest.mark.asyncio
async def test_call_intent_llm_prefers_groq():
    tool = ToolCall(tool="list_accounts", arguments={})
    with (
        patch("app.agent.llm.groq_configured", new_callable=AsyncMock, return_value=True),
        patch("app.agent.llm.call_groq", new_callable=AsyncMock, return_value=tool) as groq,
        patch("app.agent.llm.call_ollama", new_callable=AsyncMock) as ollama,
    ):
        result, source = await call_intent_llm("quais minhas contas")
    assert result == tool
    assert source == "groq"
    groq.assert_awaited_once()
    ollama.assert_not_awaited()


@pytest.mark.asyncio
async def test_call_intent_llm_falls_back_to_ollama():
    tool = ToolCall(tool="get_summary", arguments={})
    with (
        patch("app.agent.llm.groq_configured", new_callable=AsyncMock, return_value=True),
        patch(
            "app.agent.llm.call_groq",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPError("down"),
        ),
        patch("app.agent.llm.call_ollama", new_callable=AsyncMock, return_value=tool) as ollama,
    ):
        result, source = await call_intent_llm("resumo do mes")
    assert result == tool
    assert source == "ollama"
    ollama.assert_awaited_once()
