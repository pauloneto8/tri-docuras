"""Wizard conversacional para cadastro de cartão de crédito."""

from __future__ import annotations

from app.schemas import AgentResponse, ToolCall
from app.services.account_wizard import is_cancel
from app.services.agent_suggestions import for_card_wizard_field
from app.services.intents import detect_card_creation, wants_card_creation, wants_list_accounts
from app.services.tools import parse_amount
from app.services.wizard_slots import is_complex_message, is_short_slot_message

WIZARD_KEY = "card_wizard"

QUESTIONS = {
    "name": "Qual o apelido do cartão? (ex.: Nubank, Itaú Cartão)",
    "institution": "Qual a instituição? (opcional — responda 'pular' para ignorar)",
    "closing_day": "Qual o *dia de fechamento* da fatura? (1 a 31)",
    "due_day": "Qual o *dia de vencimento* da fatura? (1 a 31)",
    "credit_limit": "Qual o *limite* do cartão? (opcional — responda 'pular' para ignorar)",
    "settlement_account_name": (
        "Qual a *conta de liquidação* padrão? "
        "(conta usada para pagar a fatura — você poderá alterar no pagamento)"
    ),
}

SKIP_WORDS = {"pular", "nao", "não", "nenhum", "nenhuma", "sem", "-", "skip"}


def _coerce_day(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if 1 <= value <= 31 else None
    if isinstance(value, str):
        from app.services.credit_cards import parse_day_of_month

        if not value.strip():
            return None
        return parse_day_of_month(value)
    return None


def _normalize_initial_value(key: str, value):
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    if key in {"closing_day", "due_day"}:
        return _coerce_day(value)
    if key == "name":
        text = str(value).strip()
        return text if len(text) >= 2 else None
    if key == "settlement_account_name":
        text = str(value).strip()
        return text if len(text) >= 2 else None
    return value


def _sanitize_initial(initial: dict | None) -> dict:
    if not initial:
        return {}
    sanitized: dict = {}
    for key in (
        "name",
        "institution",
        "closing_day",
        "due_day",
        "credit_limit",
        "settlement_account_name",
    ):
        if key not in initial:
            continue
        normalized = _normalize_initial_value(key, initial[key])
        if normalized is not None:
            sanitized[key] = normalized
    return sanitized


def _normalize_wizard(wizard: dict) -> None:
    wizard["closing_day"] = _coerce_day(wizard.get("closing_day"))
    wizard["due_day"] = _coerce_day(wizard.get("due_day"))
    name = wizard.get("name")
    if isinstance(name, str):
        name = name.strip()
        wizard["name"] = name if len(name) >= 2 else None
    settlement = wizard.get("settlement_account_name")
    if isinstance(settlement, str):
        settlement = settlement.strip()
        wizard["settlement_account_name"] = settlement if len(settlement) >= 2 else None


def _confirmation_response(
    wizard: dict, *, db=None, user_id: int | None = None
) -> AgentResponse:
    _normalize_wizard(wizard)
    remaining = _next_field(wizard)
    if remaining is not None:
        return _ask_field(remaining, db=db, user_id=user_id)
    return AgentResponse(
        message=_wizard_summary(wizard),
        needs_confirmation=True,
        pending_action=wizard_to_tool_call(wizard).model_dump(),
        tool_used="create_card",
        source="wizard",
    )


def is_skip(message: str) -> bool:
    return message.strip().lower() in SKIP_WORDS


def get_wizard(session: dict) -> dict | None:
    return session.get(WIZARD_KEY)


def clear_wizard(session: dict) -> None:
    session.pop(WIZARD_KEY, None)


def start_wizard(session: dict, initial: dict | None = None) -> None:
    data = {
        "name": None,
        "institution": None,
        "closing_day": None,
        "due_day": None,
        "credit_limit": None,
        "settlement_account_name": None,
        "institution_asked": False,
        "credit_limit_asked": False,
    }
    sanitized = _sanitize_initial(initial)
    for key in (
        "name",
        "institution",
        "closing_day",
        "due_day",
        "credit_limit",
        "settlement_account_name",
    ):
        if sanitized.get(key) is not None:
            data[key] = sanitized[key]
    if sanitized.get("institution"):
        data["institution_asked"] = True
    if sanitized.get("credit_limit") is not None:
        data["credit_limit_asked"] = True
    _normalize_wizard(data)
    session[WIZARD_KEY] = data


def _next_field(wizard: dict) -> str | None:
    _normalize_wizard(wizard)
    if not wizard.get("name"):
        return "name"
    if not wizard.get("institution_asked"):
        return "institution"
    if _coerce_day(wizard.get("closing_day")) is None:
        return "closing_day"
    if _coerce_day(wizard.get("due_day")) is None:
        return "due_day"
    if not wizard.get("credit_limit_asked"):
        return "credit_limit"
    if not wizard.get("settlement_account_name"):
        return "settlement_account_name"
    return None


def _fill_field(wizard: dict, field: str, message: str) -> str | None:
    if field == "name":
        value = message.strip()
        if len(value) < 2:
            return "Informe um apelido com pelo menos 2 caracteres."
        wizard["name"] = value[:100]
        return None

    if field == "institution":
        wizard["institution_asked"] = True
        if is_skip(message):
            wizard["institution"] = None
        else:
            wizard["institution"] = message.strip()[:100]
        return None

    if field == "closing_day":
        from app.services.credit_cards import parse_day_of_month

        parsed = parse_day_of_month(message)
        if parsed is None:
            return "Dia inválido. Informe um número de 1 a 31."
        wizard["closing_day"] = parsed
        return None

    if field == "due_day":
        from app.services.credit_cards import parse_day_of_month

        parsed = parse_day_of_month(message)
        if parsed is None:
            return "Dia inválido. Informe um número de 1 a 31."
        wizard["due_day"] = parsed
        return None

    if field == "credit_limit":
        wizard["credit_limit_asked"] = True
        if is_skip(message):
            wizard["credit_limit"] = None
        else:
            amount = parse_amount(message) or message.strip()
            try:
                from app.schemas import decimal_to_cents

                cents = decimal_to_cents(amount)
                if cents <= 0:
                    wizard["credit_limit"] = None
                else:
                    wizard["credit_limit"] = amount
            except (ValueError, Exception):
                return "Valor inválido. Informe o limite ou responda 'pular'."
        return None

    if field == "settlement_account_name":
        value = message.strip()
        if len(value) < 2:
            return "Informe o nome da conta de liquidação."
        wizard["settlement_account_name"] = value[:100]
        return None

    return "Campo desconhecido."


def _wizard_summary(wizard: dict) -> str:
    lines = [
        f"Apelido: {wizard['name']}",
        f"Fechamento: dia {wizard.get('closing_day')}",
        f"Vencimento: dia {wizard.get('due_day')}",
        f"Conta de liquidação: {wizard.get('settlement_account_name')}",
    ]
    if wizard.get("institution"):
        lines.insert(1, f"Instituição: {wizard['institution']}")
    if wizard.get("credit_limit"):
        lines.append(f"Limite: R$ {wizard['credit_limit']}")
    return "Confirme o cadastro do cartão:\n" + "\n".join(lines)


def wizard_to_tool_call(wizard: dict) -> ToolCall:
    closing_day = _coerce_day(wizard.get("closing_day"))
    due_day = _coerce_day(wizard.get("due_day"))
    if not wizard.get("name") or closing_day is None or due_day is None:
        raise ValueError("Dados incompletos para cadastrar o cartão.")
    if not wizard.get("settlement_account_name"):
        raise ValueError("Conta de liquidação é obrigatória.")
    args = {
        "name": wizard["name"],
        "closing_day": closing_day,
        "due_day": due_day,
        "settlement_account_name": wizard["settlement_account_name"],
    }
    if wizard.get("institution"):
        args["institution"] = wizard["institution"]
    if wizard.get("credit_limit"):
        args["credit_limit"] = wizard["credit_limit"]
    return ToolCall(tool="create_card", arguments=args)


def is_slot_answer(message: str, field: str) -> bool:
    if is_complex_message(message):
        return False
    if field == "name":
        return len(message.strip()) >= 2 and is_short_slot_message(message, max_words=6)
    if field == "institution":
        return is_skip(message) or is_short_slot_message(message, max_words=6)
    if field in {"closing_day", "due_day"}:
        from app.services.credit_cards import parse_day_of_month

        return parse_day_of_month(message) is not None
    if field == "credit_limit":
        return is_skip(message) or bool(parse_amount(message))
    if field == "settlement_account_name":
        return is_short_slot_message(message, max_words=6)
    return False


def get_wizard_context(session: dict) -> str | None:
    wizard = get_wizard(session)
    if not wizard:
        return None
    field = _next_field(wizard)
    if not field:
        return "Wizard de cartao aguardando confirmacao"
    labels = {
        "name": "apelido do cartao",
        "institution": "instituicao",
        "closing_day": "dia de fechamento",
        "due_day": "dia de vencimento",
        "credit_limit": "limite",
        "settlement_account_name": "conta de liquidacao",
    }
    return f"Wizard de cartao aguardando: {labels.get(field, field)}"


def _ask_field(field: str, message: str | None = None, *, db=None, user_id: int | None = None) -> AgentResponse:
    return AgentResponse(
        message=message or QUESTIONS[field],
        suggestions=for_card_wizard_field(field, db, user_id),
        source="wizard",
    )


def process_wizard_message(
    session: dict, message: str, *, db=None, user_id: int | None = None
) -> AgentResponse | None:
    wizard = get_wizard(session)
    if not wizard:
        return None

    if is_cancel(message):
        clear_wizard(session)
        return AgentResponse(message="Cadastro de cartão cancelado.", clear_wizard=True, source="wizard")

    if wants_list_accounts(message):
        clear_wizard(session)
        return None

    next_field = _next_field(wizard)
    if next_field is None:
        lower = message.strip().lower()
        if lower in {"sim", "s", "ok", "confirmo", "isso", "essa", "esse", "confirmar"}:
            return _confirmation_response(wizard, db=db, user_id=user_id)
        clear_wizard(session)
        return None

    if next_field == "settlement_account_name" and db is not None and user_id is not None:
        from app.services.transaction_slots import list_active_account_names, parse_account_answer

        accounts = list_active_account_names(db, user_id)
        parsed = parse_account_answer(message, accounts)
        if parsed:
            wizard["settlement_account_name"] = parsed
            session[WIZARD_KEY] = wizard
            return _confirmation_response(wizard, db=db, user_id=user_id)
        if is_slot_answer(message, next_field):
            error = _fill_field(wizard, next_field, message)
            if error:
                session[WIZARD_KEY] = wizard
                return _ask_field(next_field, error, db=db, user_id=user_id)
            session[WIZARD_KEY] = wizard
            return _confirmation_response(wizard, db=db, user_id=user_id)
        return _ask_field(
            next_field,
            "Conta não encontrada. Escolha uma das contas listadas ou informe o nome exato.",
            db=db,
            user_id=user_id,
        )

    if not is_slot_answer(message, next_field):
        if is_complex_message(message):
            clear_wizard(session)
            return None
        return _ask_field(
            next_field,
            f"Não entendi. {QUESTIONS[next_field]}",
            db=db,
            user_id=user_id,
        )

    error = _fill_field(wizard, next_field, message)
    if error:
        session[WIZARD_KEY] = wizard
        return _ask_field(next_field, error, db=db, user_id=user_id)

    session[WIZARD_KEY] = wizard
    remaining = _next_field(wizard)
    if remaining is None:
        return _confirmation_response(wizard, db=db, user_id=user_id)
    return _ask_field(remaining, db=db, user_id=user_id)


def try_process_card_wizard(
    session: dict, message: str, *, db=None, user_id: int | None = None
) -> AgentResponse | None:
    if not get_wizard(session):
        return None
    if wants_card_creation(message) and not is_cancel(message):
        clear_wizard(session)
        return begin_card_wizard(session, message, db=db, user_id=user_id)
    return process_wizard_message(session, message, db=db, user_id=user_id)


def begin_card_wizard(
    session: dict,
    message: str,
    initial: dict | None = None,
    *,
    db=None,
    user_id: int | None = None,
) -> AgentResponse:
    extracted = detect_card_creation(message) or {}
    merged = {**extracted, **_sanitize_initial(initial)}
    start_wizard(session, merged)
    wizard = get_wizard(session)
    assert wizard is not None
    session[WIZARD_KEY] = wizard

    next_field = _next_field(wizard)
    if next_field is None:
        return _confirmation_response(wizard, db=db, user_id=user_id)
    return _ask_field(next_field, db=db, user_id=user_id)
