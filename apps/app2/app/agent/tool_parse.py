from pydantic import ValidationError

from app.schemas import ToolCall

KNOWN_TOOLS = frozenset(
    {
        "register_expense",
        "register_income",
        "register_transfer",
        "realize_planned",
        "update_transaction",
        "delete_transaction",
        "update_account",
        "list_transactions",
        "list_accounts",
        "list_categories",
        "get_summary",
        "get_budget_status",
        "categorize",
        "create_account",
        "create_category",
        "unsupported_action",
    }
)

DEFAULT_UNSUPPORTED_MESSAGE = (
    "Essa ação ainda não está disponível no assistente. "
    "Posso ajudar a: lançar despesas e receitas (incluindo previsões), realizar previsões, "
    "corrigir ou excluir lançamentos, editar contas (saldo inicial, apelido), "
    "listar contas, categorias e transações, ver resumo do mês, cadastrar contas ou categorias."
)


def unsupported_tool_call(
    *,
    reason: str | None = None,
    requested_tool: str | None = None,
) -> ToolCall:
    if reason:
        message = reason
    elif requested_tool:
        message = (
            f"A ação '{requested_tool}' ainda não está disponível no assistente. "
            "Posso ajudar a: lançar despesas e receitas, corrigir ou excluir lançamentos, "
            "editar contas (saldo inicial, apelido), listar contas, categorias e transações, "
            "ver resumo do mês, cadastrar contas ou cadastrar categorias."
        )
    else:
        message = DEFAULT_UNSUPPORTED_MESSAGE
    return ToolCall(tool="unsupported_action", arguments={"reason": message})


def parse_tool_call(parsed: dict | None) -> ToolCall | None:
    if not parsed or not isinstance(parsed, dict):
        return None

    tool = parsed.get("tool")
    arguments = parsed.get("arguments")
    if not tool:
        return None
    if arguments is None:
        parsed = {**parsed, "arguments": {}}
    elif not isinstance(arguments, dict):
        return None

    if tool not in KNOWN_TOOLS:
        return unsupported_tool_call(requested_tool=str(tool))

    try:
        return ToolCall(**parsed)
    except ValidationError:
        if tool == "unsupported_action":
            reason = (parsed.get("arguments") or {}).get("reason")
            return unsupported_tool_call(reason=reason)
        return unsupported_tool_call(requested_tool=str(tool))
