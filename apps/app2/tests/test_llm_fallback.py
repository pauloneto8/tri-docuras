from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.agent.llm import call_claude_intent_llm, call_llm
from app.schemas import ToolCall


@pytest.mark.asyncio
async def test_call_llm_uses_groq():
    tool = ToolCall(tool="get_summary", arguments={})
    with (
        patch("app.agent.llm.groq_configured", new_callable=AsyncMock, return_value=True),
        patch("app.agent.llm.call_groq", new_callable=AsyncMock, return_value=tool),
    ):
        result, source = await call_llm("resumo do mes")
    assert result == tool
    assert source == "groq"


@pytest.mark.asyncio
async def test_call_llm_returns_none_when_groq_fails():
    with (
        patch("app.agent.llm.groq_configured", new_callable=AsyncMock, return_value=True),
        patch(
            "app.agent.llm.call_groq",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPError("down"),
        ),
    ):
        result, source = await call_llm("ultimas transacoes")
    assert result is None
    assert source == "groq"


@pytest.mark.asyncio
async def test_call_llm_returns_none_when_groq_not_configured():
    with patch("app.agent.llm.groq_configured", new_callable=AsyncMock, return_value=False):
        result, source = await call_llm("resumo")
    assert result is None
    assert source == "groq"


@pytest.mark.asyncio
async def test_call_claude_intent_llm_noop_when_flag_disabled():
    with patch("app.agent.llm.settings") as settings:
        settings.enable_ai_nlu_fallback = False
        result, source = await call_claude_intent_llm("compra estranha de 45 reais")
    assert result is None
    assert source == "claude-fallback"


@pytest.mark.asyncio
async def test_call_claude_intent_llm_noop_when_not_configured():
    with (
        patch("app.agent.llm.settings") as settings,
        patch("app.agent.llm.claude_configured", new_callable=AsyncMock, return_value=False),
    ):
        settings.enable_ai_nlu_fallback = True
        result, source = await call_claude_intent_llm("compra estranha de 45 reais")
    assert result is None
    assert source == "claude-fallback"


@pytest.mark.asyncio
async def test_call_claude_intent_llm_uses_claude_when_enabled():
    tool = ToolCall(tool="get_summary", arguments={})
    with (
        patch("app.agent.llm.settings") as settings,
        patch("app.agent.llm.claude_configured", new_callable=AsyncMock, return_value=True),
        patch(
            "app.agent.llm.call_claude_tool_call", new_callable=AsyncMock, return_value=tool
        ) as claude,
    ):
        settings.enable_ai_nlu_fallback = True
        result, source = await call_claude_intent_llm("compra estranha de 45 reais")
    assert result == tool
    assert source == "claude-fallback"
    claude.assert_awaited_once()


@pytest.mark.asyncio
async def test_call_claude_intent_llm_returns_none_when_claude_fails():
    with (
        patch("app.agent.llm.settings") as settings,
        patch("app.agent.llm.claude_configured", new_callable=AsyncMock, return_value=True),
        patch(
            "app.agent.llm.call_claude_tool_call",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPError("down"),
        ),
    ):
        settings.enable_ai_nlu_fallback = True
        result, source = await call_claude_intent_llm("compra estranha de 45 reais")
    assert result is None
    assert source == "claude-fallback"
