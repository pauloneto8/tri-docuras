import httpx

from app.agent.prompt import SYSTEM_PROMPT, extract_json
from app.agent.tool_parse import parse_tool_call
from app.config import settings
from app.schemas import ToolCall


async def call_ollama(user_message: str, *, system_prompt: str | None = None) -> ToolCall | None:
    payload = {
        "model": settings.ollama_model,
        "messages": [
            {"role": "system", "content": system_prompt or SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 256},
    }
    async with httpx.AsyncClient(timeout=90.0) as client:
        response = await client.post(
            f"{settings.ollama_url}/api/chat",
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
    content = data.get("message", {}).get("content", "")
    parsed = extract_json(content)
    return parse_tool_call(parsed)


async def ensure_model_available() -> bool:
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(f"{settings.ollama_url}/api/tags")
            response.raise_for_status()
            models = [m["name"] for m in response.json().get("models", [])]
            target = settings.ollama_model
            return any(target in name or name.startswith(target.split(":")[0]) for name in models)
        except httpx.HTTPError:
            return False
