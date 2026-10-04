import asyncio
import logging

import httpx

from app.agent.prompt import SYSTEM_PROMPT, extract_json
from app.agent.tool_parse import parse_tool_call
from app.config import settings
from app.schemas import ToolCall

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# Limite de taxa do Groq devolve 429 com pouca frequência; espera antes de desistir.
MAX_ATTEMPTS = 5
BACKOFF_BASE_SECONDS = 2.0
MAX_BACKOFF_SECONDS = 30.0
RETRY_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class GroqRateLimitError(httpx.HTTPStatusError):
    """429 do Groq que persistiu depois de todas as tentativas.

    Separado dos demais erros para o chamador cair no fallback legado sem
    registrar traceback: rate limit é esperado, não é falha do agente.
    """


async def groq_configured() -> bool:
    return bool(settings.groq_api_key.strip())


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    raw = (response.headers.get("retry-after") or "").strip()
    try:
        if raw:
            return min(float(raw), MAX_BACKOFF_SECONDS)
    except ValueError:
        pass
    return min(BACKOFF_BASE_SECONDS * (2**attempt), MAX_BACKOFF_SECONDS)


async def _post_json(client: httpx.AsyncClient, payload: dict) -> dict:
    """POST na API do Groq com retry/backoff em rate limit e 5xx."""
    headers = {
        "Authorization": f"Bearer {settings.groq_api_key}",
        "Content-Type": "application/json",
    }
    last_error: httpx.HTTPStatusError | None = None
    for attempt in range(MAX_ATTEMPTS):
        response = await client.post(GROQ_API_URL, json=payload, headers=headers)
        if response.status_code not in RETRY_STATUS:
            response.raise_for_status()
            return response.json()
        last_error = httpx.HTTPStatusError(
            f"{response.status_code} do Groq",
            request=response.request,
            response=response,
        )
        if attempt == MAX_ATTEMPTS - 1:
            break
        delay = _retry_delay(response, attempt)
        logger.warning(
            "Groq %s (tentativa %s/%s); nova tentativa em %.1fs",
            response.status_code,
            attempt + 1,
            MAX_ATTEMPTS,
            delay,
        )
        await asyncio.sleep(delay)
    assert last_error is not None
    assert last_error.response is not None
    if last_error.response.status_code == 429:
        raise GroqRateLimitError(
            f"{last_error.response.status_code} do Groq após {MAX_ATTEMPTS} tentativas",
            request=last_error.request,
            response=last_error.response,
        ) from last_error
    raise last_error


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
    async with httpx.AsyncClient(timeout=60.0) as client:
        data = await _post_json(client, payload)

    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    parsed = extract_json(content)
    return parse_tool_call(parsed)


async def call_groq_text(
    user_message: str,
    *,
    system_prompt: str | None = None,
    max_tokens: int = 300,
    temperature: float = 0.3,
) -> str | None:
    """Chat Completions simples (sem ferramentas) — devolve texto puro."""
    if not await groq_configured():
        return None

    payload = {
        "model": settings.groq_model,
        "messages": [
            {"role": "system", "content": system_prompt or SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        data = await _post_json(client, payload)

    return (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()


async def chat_with_tools(
    messages: list,
    tools: list | None = None,
    *,
    tool_choice: str = "auto",
    parallel_tool_calls: bool = True,
    temperature: float = 0.1,
    max_tokens: int = 1500,
) -> dict:
    """Chat Completions do Groq com ferramentas. Devolve a `message` do assistente.

    A message pode conter `content` e/ou `tool_calls` (formato OpenAI). O loop
    agêntico (brain.py) interpreta as tool_calls. Se não houver chave, devolve
    mensagem vazia para o chamador cair no fluxo normal.
    """
    if not await groq_configured():
        return {"role": "assistant", "content": ""}

    payload: dict = {
        "model": settings.groq_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice
        payload["parallel_tool_calls"] = parallel_tool_calls

    async with httpx.AsyncClient(timeout=60.0) as client:
        data = await _post_json(client, payload)

    return data.get("choices", [{}])[0].get("message", {}) or {"role": "assistant", "content": ""}
