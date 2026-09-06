from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.agent.llm import call_intent_llm
from app.schemas import ToolCall


@pytest.mark.asyncio
async def test_call_intent_llm_uses_groq():
    tool = ToolCall(tool="list_accounts", arguments={})
    with (
        patch("app.agent.llm.groq_configured", new_callable=AsyncMock, return_value=True),
        patch("app.agent.llm.call_groq", new_callable=AsyncMock, return_value=tool) as groq,
    ):
        result, source = await call_intent_llm("quais minhas contas")
    assert result == tool
    assert source == "groq"
    groq.assert_awaited_once()


@pytest.mark.asyncio
async def test_call_intent_llm_returns_none_when_groq_fails():
    with (
        patch("app.agent.llm.groq_configured", new_callable=AsyncMock, return_value=True),
        patch(
            "app.agent.llm.call_groq",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPError("down"),
        ),
    ):
        result, source = await call_intent_llm("resumo do mes")
    assert result is None
    assert source == "groq"
