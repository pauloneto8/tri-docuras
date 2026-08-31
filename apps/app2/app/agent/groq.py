import httpx

from app.agent.prompt import SYSTEM_PROMPT, extract_json
from app.agent.tool_parse import parse_tool_call
from app.config import settings
from app.schemas import ToolCall

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


async def groq_configured() -> bool:
    return bool(settings.groq_api_key.strip())


async def call_groq(user_message: str, *, system_prompt: str | None = None) -> ToolCall | None:
    if not await groq_configured():
        return None

    payload = {
        "model": settings.groq_model,
        "messages": [
            {"role": "system", "content": system_prompt or SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.1,
        "max_tokens": 512,
    }
    headers = {
        "Authorization": f"Bearer {settings.groq_api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(GROQ_API_URL, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    parsed = extract_json(content)
    return parse_tool_call(parsed)
