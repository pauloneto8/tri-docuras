from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.agent.llm import call_llm
from app.schemas import ToolCall


@pytest.mark.asyncio
async def test_call_llm_uses_ollama_when_available():
    tool = ToolCall(tool="get_summary", arguments={})
    with patch("app.agent.llm.call_ollama", new_callable=AsyncMock, return_value=tool):
        result, source = await call_llm("resumo do mes")
    assert result == tool
    assert source == "ollama"


@pytest.mark.asyncio
async def test_call_llm_falls_back_to_groq_when_ollama_fails():
    tool = ToolCall(tool="list_transactions", arguments={"limit": 5})
    with (
        patch(
            "app.agent.llm.call_ollama",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPError("down"),
        ),
        patch("app.agent.llm.groq_configured", new_callable=AsyncMock, return_value=True),
        patch("app.agent.llm.call_groq", new_callable=AsyncMock, return_value=tool),
    ):
        result, source = await call_llm("ultimas transacoes")
    assert result == tool
    assert source == "groq"
