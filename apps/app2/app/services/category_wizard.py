import re

from app.schemas import AgentResponse, ToolCall
from app.services.agent_suggestions import for_category_wizard_field
from app.services.intents import detect_category_creation, wants_category_creation, wants_list_categories
from app.services.text_correction import correct_category_name
from app.services.wizard_slots import is_complex_message, is_short_slot_message

WIZARD_KEY = "category_wizard"
CANCEL_WORDS = {"cancelar", "desistir", "abortar", "sair"}

EXPENSE_TYPE_WORDS = ("despesa", "despesas", "gasto", "gastos", "debito", "débito")
INCOME_TYPE_WORDS = ("receita", "receitas", "entrada", "entradas", "credito", "crédito")

FIELD_ORDER = ("name", "category_type")

QUESTIONS = {
    "name": "Qual o nome da nova categoria? (ex.: Pet, Assinaturas, Freelance)",
    "category_type": "É categoria de *despesa* ou de *receita*?",
}

TYPE_LABELS = {
    "expense": "Despesa",
    "income": "Receita",
}


def get_wizard(session: dict) -> dict | None:
    return session.get(WIZARD_KEY)


def clear_wizard(session: dict) -> None:
    session.pop(WIZARD_KEY, None)


def _parse_category_type(text: str) -> str | None:
    lower = text.lower()
    has_expense = any(w in lower for w in EXPENSE_TYPE_WORDS)
    has_income = any(w in lower for w in INCOME_TYPE_WORDS)
    if has_expense and not has_income:
        return "expense"
    if has_income and not has_expense:
        return "income"
    if lower.strip() in {"despesa", "despesas", "1"}:
        return "expense"
    if lower.strip() in {"receita", "receitas", "2"}:
        return "income"
    return None


def start_wizard(session: dict, initial: dict | None = None) -> None:
    data = {
        "name": None,
        "category_type": None,
        "keywords": None,
    }
    if initial:
        if initial.get("name"):
            data["name"] = correct_category_name(str(initial["name"]))[:100]
        if initial.get("type"):
            data["category_type"] = initial["type"]
        if initial.get("keywords"):
            data["keywords"] = str(initial["keywords"]).strip()[:500]
    session[WIZARD_KEY] = data


def _next_field(wizard: dict) -> str | None:
    if not wizard.get("name"):
        return "name"
    if not wizard.get("category_type"):
        return "category_type"
    return None


def _fill_field(wizard: dict, field: str, message: str) -> str | None:
    if field == "name":
        name = correct_category_name(message.strip())
        if len(name) < 2:
            return "Informe um nome com pelo menos 2 caracteres."
        wizard["name"] = name[:100]
        return None
    if field == "category_type":
        category_type = _parse_category_type(message)
        if not category_type:
            return "Responda com *despesa* ou *receita*."
        wizard["category_type"] = category_type
        return None
    return "Campo desconhecido."


def is_slot_answer(message: str, field: str) -> bool:
    if is_complex_message(message):
        return False
    if field == "name":
        text = message.strip()
        return len(text) >= 2 and is_short_slot_message(text, max_words=6)
    if field == "category_type":
        return _parse_category_type(message) is not None
    return False


def _wizard_summary(wizard: dict) -> str:
    type_label = TYPE_LABELS.get(wizard["category_type"], wizard["category_type"])
    lines = [
        f"Confirmar cadastro da categoria '{wizard['name']}' ({type_label})?",
    ]
    if wizard.get("keywords"):
        lines.append(f"Palavras-chave: {wizard['keywords']}.")
    lines.append("Clique em Confirmar para cadastrar.")
    return " ".join(lines)


def wizard_to_tool_call(wizard: dict) -> ToolCall:
    args = {
        "name": wizard["name"],
        "type": wizard["category_type"],
    }
    if wizard.get("keywords"):
        args["keywords"] = wizard["keywords"]
    return ToolCall(tool="create_category", arguments=args)


def get_wizard_context(session: dict) -> str | None:
    wizard = get_wizard(session)
    if not wizard:
        return None
    field = _next_field(wizard)
    if not field:
        return "Wizard de categoria aguardando confirmacao"
    labels = {
        "name": "nome da categoria",
        "category_type": "tipo (despesa ou receita)",
    }
    return f"Wizard de categoria aguardando: {labels.get(field, field)}"


def _ask_field(field: str, message: str | None = None) -> AgentResponse:
    return AgentResponse(
        message=message or QUESTIONS[field],
        suggestions=for_category_wizard_field(field),
        source="wizard",
    )


def process_wizard_message(session: dict, message: str) -> AgentResponse | None:
    wizard = get_wizard(session)
    if not wizard:
        return None

    if message.strip().lower() in CANCEL_WORDS:
        clear_wizard(session)
        from app.services.transaction_wizard import (
            restore_paused_transaction_on_category_cancel,
        )

        restored = restore_paused_transaction_on_category_cancel(session)
        if restored:
            return restored
        return AgentResponse(message="Cadastro de categoria cancelado.", clear_wizard=True, source="wizard")

    if wants_list_categories(message):
        clear_wizard(session)
        return None

    next_field = _next_field(wizard)
    if next_field is None:
        lower = message.strip().lower()
        if lower in {"sim", "s", "ok", "confirmo", "isso", "essa", "esse"}:
            return AgentResponse(
                message=_wizard_summary(wizard),
                needs_confirmation=True,
                pending_action=wizard_to_tool_call(wizard).model_dump(),
                tool_used="create_category",
                source="wizard",
            )
        clear_wizard(session)
        return None

    if not is_slot_answer(message, next_field):
        clear_wizard(session)
        return None

    error = _fill_field(wizard, next_field, message)
    if error:
        session[WIZARD_KEY] = wizard
        return _ask_field(next_field, error)

    session[WIZARD_KEY] = wizard
    remaining = _next_field(wizard)
    if remaining is None:
        return AgentResponse(
            message=_wizard_summary(wizard),
            needs_confirmation=True,
            pending_action=wizard_to_tool_call(wizard).model_dump(),
            tool_used="create_category",
            source="wizard",
        )
    return _ask_field(remaining)


def try_process_category_wizard(session: dict, message: str) -> AgentResponse | None:
    if not get_wizard(session):
        return None
    if wants_category_creation(message) and message.strip().lower() not in CANCEL_WORDS:
        clear_wizard(session)
        return begin_category_wizard(session, message)
    return process_wizard_message(session, message)


def begin_category_wizard(
    session: dict, message: str, initial: dict | None = None
) -> AgentResponse:
    extracted = detect_category_creation(message) or {}
    merged = {**extracted, **(initial or {})}
    start_wizard(session, merged)
    wizard = get_wizard(session)
    assert wizard is not None
    session[WIZARD_KEY] = wizard

    next_field = _next_field(wizard)
    if next_field is None:
        return AgentResponse(
            message=_wizard_summary(wizard),
            needs_confirmation=True,
            pending_action=wizard_to_tool_call(wizard).model_dump(),
            tool_used="create_category",
            source="wizard",
        )
    return _ask_field(next_field)
