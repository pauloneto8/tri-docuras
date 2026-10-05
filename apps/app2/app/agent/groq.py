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
    `attempts` é quantas chamadas foram realmente feitas (1 quando o orçamento
    diário acabou e não há retry possível).
    """

    attempts: int = MAX_ATTEMPTS


def _is_daily_quota(response: httpx.Response) -> bool:
    """Distingue 429 por minuto (429 passageiro) de 429 por dia (orçamento do dia).

    O tier free do gpt-oss-120b tem 8.000 tokens/min e 200.000 tokens/dia. Quando
    é o dia que estourou, repetir a chamada não adianta dentro da janela: a espera
    só segura o usuário por ~2 minutos antes do fallback legado. Nesse caso o erro
    sobe na primeira resposta.
    """
    if response.status_code != 429:
        return False
    body = response.text.lower()
    return "tokens per day" in body or "(tpd)" in body


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
    attempts = 0
    for attempt in range(MAX_ATTEMPTS):
        attempts = attempt + 1
        response = await client.post(GROQ_API_URL, json=payload, headers=headers)
        if response.status_code not in RETRY_STATUS:
            response.raise_for_status()
            return response.json()
        last_error = httpx.HTTPStatusError(
            f"{response.status_code} do Groq",
            request=response.request,
            response=response,
        )
        if _is_daily_quota(response):
            logger.warning(
                "Groq: orcamento diario de tokens (TPD) esgotado; sem nova tentativa "
                "nesta janela"
            )
            break
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
        error = GroqRateLimitError(
            f"{last_error.response.status_code} do Groq após {attempts} tentativas",
            request=last_error.request,
            response=last_error.response,
        )
        error.attempts = attempts
        raise error from last_error
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

    `usage` da resposta vai junto na message (chave `usage`): o orçamento do Groq
    free é por tokens, então o loop precisa saber quanto cada chamada custou.
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

    message = data.get("choices", [{}])[0].get("message", {}) or {}
    out = dict(message)
    out["usage"] = data.get("usage") or {}
    return out
