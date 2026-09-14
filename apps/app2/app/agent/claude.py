import httpx

from app.config import settings

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

# Chamada HTTP direta (mesmo padrão de app/agent/groq.py) em vez do SDK oficial
# da Anthropic: mantém a dependência mínima já escolhida para o agente (um
# único cliente httpx assíncrono para os dois provedores) e evita rebuild de
# imagem só para adicionar um SDK usado numa única chamada simples.
#
# Usado apenas para tarefas de raciocínio/explicação (insight financeiro,
# fallback de linguagem livre) — nunca para decidir ferramentas de escrita.
# O modelo nunca recebe acesso a `execute_tool`; só texto e números que o
# Python já calculou.


async def claude_configured() -> bool:
    return bool(settings.anthropic_api_key.strip())


async def call_claude(
    user_message: str,
    *,
    system_prompt: str,
    model: str | None = None,
    max_tokens: int = 512,
) -> str | None:
    """Chama a API de Mensagens da Claude e retorna o texto da resposta.

    Retorna None se a chave não estiver configurada ou se a resposta não
    tiver bloco de texto. Erros de HTTP propagam para o chamador decidir o
    fallback (mesmo contrato de `call_groq`).
    """
    if not await claude_configured():
        return None

    payload = {
        "model": model or settings.anthropic_model_fast,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_message}],
        "max_tokens": max_tokens,
    }
    headers = {
        "x-api-key": settings.anthropic_api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(ANTHROPIC_API_URL, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

    blocks = data.get("content", [])
    text = "".join(block.get("text", "") for block in blocks if block.get("type") == "text")
    text = text.strip()
    return text or None
