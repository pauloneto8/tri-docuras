import httpx

from app.agent.claude import call_claude_tool_call, claude_configured
from app.agent.groq import call_groq, groq_configured
from app.config import settings
from app.schemas import ToolCall


def _build_user_prompt(user_message: str, context: str | None) -> str:
    if not context:
        return user_message
    return (
        f"--- Contexto do usuario ---\n{context}\n\n"
        f"--- Mensagem do usuario ---\n{user_message}"
    )


async def call_llm(user_message: str) -> tuple[ToolCall | None, str]:
    """Chama Groq para interpretar a mensagem."""
    return await call_intent_llm(user_message)


async def call_intent_llm(
    user_message: str, *, context: str | None = None
) -> tuple[ToolCall | None, str]:
    """Interpreta intenção via Groq apenas."""
    prompt = _build_user_prompt(user_message, context)

    if not await groq_configured():
        return None, "groq"

    try:
        tool_call = await call_groq(prompt)
        if tool_call:
            return tool_call, "groq"
    except (httpx.HTTPError, ValueError, TypeError):
        pass

    return None, "groq"


async def call_claude_intent_llm(
    user_message: str, *, context: str | None = None
) -> tuple[ToolCall | None, str]:
    """Fallback de 3º nível (Fase 3): Claude Haiku só quando Groq e o parser
    por regra já falharam. Desligado por padrão via `ENABLE_AI_NLU_FALLBACK`
    — sem a flag e a chave, é no-op e o runner cai no "não consegui entender"
    de sempre.
    """
    if not settings.enable_ai_nlu_fallback:
        return None, "claude-fallback"

    prompt = _build_user_prompt(user_message, context)

    if not await claude_configured():
        return None, "claude-fallback"

    try:
        tool_call = await call_claude_tool_call(prompt)
        if tool_call:
            return tool_call, "claude-fallback"
    except (httpx.HTTPError, ValueError, TypeError):
        pass

    return None, "claude-fallback"


async def llm_available() -> bool:
    return await groq_configured()
