import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent.groq import call_groq, chat_with_tools
from app.schemas import ToolCall


def _client_with(response: MagicMock) -> MagicMock:
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


@pytest.mark.asyncio
async def test_chat_with_tools_devolve_usage_da_resposta():
    """O loop precisa saber quanto cada chamada custou: o Groq free é orçado em tokens."""
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "ok"}}],
        "usage": {
            "prompt_tokens": 3215,
            "completion_tokens": 42,
            "prompt_tokens_details": {"cached_tokens": 2048},
        },
    }
    client = _client_with(response)

    with (
        patch("app.agent.groq.groq_configured", new_callable=AsyncMock, return_value=True),
        patch("app.agent.groq.httpx.AsyncClient", return_value=client),
    ):
        message = await chat_with_tools([{"role": "user", "content": "oi"}], [{"type": "function"}])

    assert message["content"] == "ok"
    assert message["usage"]["prompt_tokens"] == 3215
    assert message["usage"]["prompt_tokens_details"]["cached_tokens"] == 2048


@pytest.mark.asyncio
async def test_chat_with_tools_sem_usage_nao_quebra():
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
    client = _client_with(response)

    with (
        patch("app.agent.groq.groq_configured", new_callable=AsyncMock, return_value=True),
        patch("app.agent.groq.httpx.AsyncClient", return_value=client),
    ):
        message = await chat_with_tools([{"role": "user", "content": "oi"}])

    assert message["usage"] == {}


@pytest.mark.asyncio
async def test_call_groq_parses_json_from_text_response():
    tool = ToolCall(tool="update_transaction", arguments={"description": "passagem"})
    ok_response = MagicMock()
    ok_response.status_code = 200
    ok_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": (
                        'Aqui está: {"tool":"update_transaction",'
                        '"arguments":{"description":"passagem"}}'
                    )
                }
            }
        ]
    }
    ok_response.raise_for_status = MagicMock()

    client = MagicMock()
    client.post = AsyncMock(return_value=ok_response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.agent.groq.groq_configured", new_callable=AsyncMock, return_value=True),
        patch("app.agent.groq.httpx.AsyncClient", return_value=client),
    ):
        result = await call_groq("corrija a passagem")

    assert result == tool
    payload = client.post.await_args.kwargs["json"]
    assert "response_format" not in payload
