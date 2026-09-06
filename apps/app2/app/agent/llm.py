import httpx

from app.agent.groq import call_groq, groq_configured
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


async def llm_available() -> bool:
    return await groq_configured()
