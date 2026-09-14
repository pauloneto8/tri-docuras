import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent.claude import call_claude, call_claude_tool_call, claude_configured
from app.schemas import ToolCall


@pytest.mark.asyncio
async def test_call_claude_returns_none_when_not_configured():
    with patch("app.agent.claude.claude_configured", new_callable=AsyncMock, return_value=False):
        result = await call_claude("resuma meu mes", system_prompt="sistema")

    assert result is None


@pytest.mark.asyncio
async def test_call_claude_extracts_text_block():
    ok_response = MagicMock()
    ok_response.status_code = 200
    ok_response.json.return_value = {
        "content": [{"type": "text", "text": "Voce gastou menos que o planejado."}]
    }
    ok_response.raise_for_status = MagicMock()

    client = MagicMock()
    client.post = AsyncMock(return_value=ok_response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.agent.claude.claude_configured", new_callable=AsyncMock, return_value=True),
        patch("app.agent.claude.httpx.AsyncClient", return_value=client),
    ):
        result = await call_claude("resuma meu mes", system_prompt="sistema")

    assert result == "Voce gastou menos que o planejado."
    payload = client.post.await_args.kwargs["json"]
    assert payload["system"] == "sistema"
    assert payload["messages"] == [{"role": "user", "content": "resuma meu mes"}]


@pytest.mark.asyncio
async def test_call_claude_returns_none_for_empty_content():
    ok_response = MagicMock()
    ok_response.status_code = 200
    ok_response.json.return_value = {"content": []}
    ok_response.raise_for_status = MagicMock()

    client = MagicMock()
    client.post = AsyncMock(return_value=ok_response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.agent.claude.claude_configured", new_callable=AsyncMock, return_value=True),
        patch("app.agent.claude.httpx.AsyncClient", return_value=client),
    ):
        result = await call_claude("oi", system_prompt="sistema")

    assert result is None


@pytest.mark.asyncio
async def test_call_claude_tool_call_parses_json_response():
    with (
        patch(
            "app.agent.claude.call_claude",
            new_callable=AsyncMock,
            return_value='{"tool":"get_summary","arguments":{}}',
        ) as claude,
    ):
        result = await call_claude_tool_call("resumo do mes")

    assert result == ToolCall(tool="get_summary", arguments={})
    # reaproveita o SYSTEM_PROMPT único de tool-calling por padrão
    assert claude.await_args.kwargs["system_prompt"]


@pytest.mark.asyncio
async def test_call_claude_tool_call_returns_none_without_text():
    with patch("app.agent.claude.call_claude", new_callable=AsyncMock, return_value=None):
        result = await call_claude_tool_call("oi")

    assert result is None


@pytest.mark.asyncio
async def test_call_claude_tool_call_returns_none_for_unparseable_text():
    with patch(
        "app.agent.claude.call_claude", new_callable=AsyncMock, return_value="nao e json"
    ):
        result = await call_claude_tool_call("oi")

    assert result is None
