import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent.groq import call_groq
from app.schemas import ToolCall


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
