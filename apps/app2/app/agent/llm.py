import httpx

from app.agent.groq import call_groq, groq_configured
from app.agent.ollama import call_ollama, ensure_model_available
from app.schemas import ToolCall


def _build_user_prompt(user_message: str, context: str | None) -> str:
    if not context:
        return user_message
    return (
        f"--- Contexto do usuario ---\n{context}\n\n"
        f"--- Mensagem do usuario ---\n{user_message}"
    )


async def call_llm(user_message: str) -> tuple[ToolCall | None, str]:
    """Tenta Ollama local; em falha, usa Groq como fallback."""
    try:
        tool_call = await call_ollama(user_message)
        if tool_call:
            return tool_call, "ollama"
    except (httpx.HTTPError, ValueError, TypeError):
        pass

    if await groq_configured():
        try:
            tool_call = await call_groq(user_message)
            if tool_call:
                return tool_call, "groq"
        except (httpx.HTTPError, ValueError, TypeError):
            pass

    return None, "ollama"


async def call_intent_llm(
    user_message: str, *, context: str | None = None
) -> tuple[ToolCall | None, str]:
    """Interpreta intencao: Groq primeiro, Ollama como fallback."""
    prompt = _build_user_prompt(user_message, context)

    if await groq_configured():
        try:
            tool_call = await call_groq(prompt)
            if tool_call:
                return tool_call, "groq"
        except (httpx.HTTPError, ValueError, TypeError):
            pass

    try:
        tool_call = await call_ollama(prompt)
        if tool_call:
            return tool_call, "ollama"
    except (httpx.HTTPError, ValueError, TypeError):
        pass

    source = "groq" if await groq_configured() else "ollama"
    return None, source


async def llm_available() -> bool:
    ollama_ok = await ensure_model_available()
    groq_ok = await groq_configured()
    return ollama_ok or groq_ok
