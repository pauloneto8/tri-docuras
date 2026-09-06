import re

from app.schemas import AgentResponse, ToolCall
from app.services.agent_suggestions import for_category_wizard_field
from app.services.intents import wants_category_creation, wants_list_categories
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
        "names": None,
        "category_type": None,
        "keywords": None,
    }
    if initial:
        if initial.get("names"):
            names = [
                correct_category_name(str(n))[:100]
                for n in initial["names"]
                if n and str(n).strip()
            ]
            names = [n for n in names if len(n) >= 2]
            if len(names) > 1:
                data["names"] = names
            elif len(names) == 1:
                data["name"] = names[0]
        elif initial.get("name"):
            data["name"] = correct_category_name(str(initial["name"]))[:100]
        if initial.get("type"):
            data["category_type"] = initial["type"]
        if initial.get("keywords"):
            data["keywords"] = str(initial["keywords"]).strip()[:500]
    session[WIZARD_KEY] = data


def _next_field(wizard: dict) -> str | None:
    if not wizard.get("name") and not wizard.get("names"):
        return "name"
    if not wizard.get("category_type"):
        return "category_type"
    return None


_CATEGORY_NAME_NOISE_RE = re.compile(
    r"\b(?:cadastrar|cadastre|cadastra|criar|crie|cria|adicionar|adicione|adiciona|"
    r"registrar|registre|registra|nova|novo|categoria|categorias|"
    r"(?:de\s+)?(?:despesa|despesas|receita|receitas|gasto|gastos|"
    r"entrada|entradas|debito|débito|credito|crédito))\b",
    re.IGNORECASE,
)


def extract_category_fields(message: str) -> dict:
    """Extrai nome(s)/tipo/keywords de qualquer mensagem no fluxo de categoria."""
    data: dict = {}
    category_type = _parse_category_type(message)
    if category_type:
        data["type"] = category_type

    from app.services.intents import (
        detect_category_creation,
        _extract_category_names,
        parse_category_names,
    )

    detected = detect_category_creation(message) or {}
    if detected.get("names"):
        data["names"] = detected["names"]
    elif detected.get("name"):
        data["name"] = detected["name"]
    else:
        names = _extract_category_names(message)
        if len(names) > 1:
            data["names"] = names
        elif len(names) == 1:
            data["name"] = names[0]
        else:
            cleaned = _CATEGORY_NAME_NOISE_RE.sub(" ", message.strip())
            cleaned = re.sub(r"\s+", " ", cleaned).strip(" -,.")
            # Resposta curta no slot nome (ex.: "Assinaturas" ou "A, B e C")
            if (
                cleaned
                and len(cleaned) >= 2
                and cleaned.lower() not in {"categoria", "categorias"}
            ):
                parsed = parse_category_names(cleaned)
                if len(parsed) > 1:
                    data["names"] = parsed
                elif len(parsed) == 1 and len(cleaned.split()) <= 8:
                    data["name"] = parsed[0]
    if detected.get("keywords"):
        data["keywords"] = detected["keywords"]
    return data


def _merge_category_fields(wizard: dict, data: dict) -> bool:
    changed = False
    if data.get("names") and not wizard.get("names") and not wizard.get("name"):
        wizard["names"] = [
            correct_category_name(str(n))[:100] for n in data["names"] if n
        ]
        changed = True
    if data.get("name") and not wizard.get("name") and not wizard.get("names"):
        wizard["name"] = correct_category_name(str(data["name"]))[:100]
        changed = True
    if data.get("type") and not wizard.get("category_type"):
        wizard["category_type"] = data["type"]
        changed = True
    if data.get("keywords") and not wizard.get("keywords"):
        wizard["keywords"] = str(data["keywords"]).strip()[:500]
        changed = True
    return changed


def _fill_field(wizard: dict, field: str, message: str) -> str | None:
    if field == "name":
        _merge_category_fields(wizard, extract_category_fields(message))
        if wizard.get("name") or wizard.get("names"):
            return None
        from app.services.intents import parse_category_names

        parsed = parse_category_names(message.strip())
        if len(parsed) > 1:
            wizard["names"] = parsed
            return None
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
    extracted = extract_category_fields(message)
    if field == "name" and (extracted.get("name") or extracted.get("names")):
        return True
    if field == "category_type" and (
        extracted.get("type") or _parse_category_type(message)
    ):
        return True
    if is_complex_message(message):
        return False
    if field == "name":
        text = message.strip()
        return len(text) >= 2 and is_short_slot_message(text, max_words=12)
    if field == "category_type":
        return _parse_category_type(message) is not None
    return False


def _format_names_list(names: list[str]) -> str:
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} e {names[1]}"
    return ", ".join(names[:-1]) + f" e {names[-1]}"


def _wizard_summary(wizard: dict) -> str:
    type_label = TYPE_LABELS.get(wizard["category_type"], wizard["category_type"])
    names = wizard.get("names") or ([wizard["name"]] if wizard.get("name") else [])
    if len(names) > 1:
        lines = [
            f"Confirmar cadastro de {len(names)} categorias ({type_label}): "
            f"{_format_names_list(names)}?"
        ]
    else:
        lines = [
            f"Confirmar cadastro da categoria '{names[0]}' ({type_label})?",
        ]
    if wizard.get("keywords"):
        lines.append(f"Palavras-chave: {wizard['keywords']}.")
    lines.append("Clique em Confirmar para cadastrar.")
    return " ".join(lines)


def wizard_to_tool_call(wizard: dict) -> ToolCall:
    names = wizard.get("names")
    if names and len(names) > 1:
        args: dict = {
            "names": names,
            "type": wizard["category_type"],
        }
    else:
        args = {
            "name": wizard.get("name") or (names[0] if names else ""),
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


def _confirmation(wizard: dict) -> AgentResponse:
    return AgentResponse(
        message=_wizard_summary(wizard),
        needs_confirmation=True,
        pending_action=wizard_to_tool_call(wizard).model_dump(),
        tool_used="create_category",
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
        return AgentResponse(
            message="Cadastro de categoria cancelado.",
            clear_wizard=True,
            source="wizard",
        )

    if wants_list_categories(message):
        clear_wizard(session)
        return None

    harvested_changed = _merge_category_fields(wizard, extract_category_fields(message))
    session[WIZARD_KEY] = wizard

    next_field = _next_field(wizard)
    if next_field is None:
        lower = message.strip().lower()
        if (
            lower in {"sim", "s", "ok", "confirmo", "isso", "essa", "esse"}
            or harvested_changed
        ):
            return _confirmation(wizard)
        clear_wizard(session)
        return None

    if harvested_changed and (
        (next_field == "name" and (wizard.get("name") or wizard.get("names")))
        or (next_field == "category_type" and wizard.get("category_type"))
    ):
        remaining = _next_field(wizard)
        if remaining is None:
            return _confirmation(wizard)
        return _ask_field(remaining)

    if not is_slot_answer(message, next_field):
        if harvested_changed:
            remaining = _next_field(wizard)
            if remaining is None:
                return _confirmation(wizard)
            return _ask_field(remaining)
        clear_wizard(session)
        return None

    error = _fill_field(wizard, next_field, message)
    if error:
        session[WIZARD_KEY] = wizard
        return _ask_field(next_field, error)

    session[WIZARD_KEY] = wizard
    remaining = _next_field(wizard)
    if remaining is None:
        return _confirmation(wizard)
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
    extracted = extract_category_fields(message)
    initial_clean = {
        k: v
        for k, v in (initial or {}).items()
        if v is not None and str(v).strip() != "" and not str(k).startswith("_")
    }
    # Tipo só assumido pelo fallback de regras: não pular a pergunta
    if (initial or {}).get("_type_assumed") and "type" not in extracted:
        initial_clean.pop("type", None)
    merged = {**extracted, **initial_clean}
    # Preferir tipo explícito da mensagem sobre o initial genérico
    if extracted.get("type"):
        merged["type"] = extracted["type"]
    start_wizard(session, merged)
    wizard = get_wizard(session)
    assert wizard is not None
    session[WIZARD_KEY] = wizard

    next_field = _next_field(wizard)
    if next_field is None:
        return _confirmation(wizard)
    return _ask_field(next_field)
