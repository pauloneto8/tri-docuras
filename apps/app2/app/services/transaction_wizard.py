from sqlalchemy.orm import Session

from app.schemas import AgentResponse
from app.services.agent_suggestions import for_transaction_wizard_field
from app.services.text_correction import correct_movement_description
from app.services.multi_movements import count_amounts
from app.services.tools import (
    format_pending_confirmation,
    is_relative_date_message,
    parse_amount,
    parse_date,
    strip_relative_date_tokens,
)
from app.services.transaction_slots import (
    DATE_SLOTS,
    SLOT_QUESTIONS,
    WIZARD_KEY,
    _apply_inference,
    _next_slot,
    _question_for_slot,
    _tool_call_from_wizard,
    apply_inferred_dates,
    fill_slot,
    list_active_account_names,
    list_category_names,
    parse_account_answer,
    parse_category_answer,
    parse_slot_date,
    parse_status_answer,
)
from app.services.wizard_slots import is_complex_message, is_short_slot_message

PROMPT_FLAG = "prompt_transaction_on_login"

CANCEL_WORDS = {"cancelar", "desistir", "abortar", "sair", "não", "nao"}
EXPENSE_WORDS = {"despesa", "despesas", "gasto", "gastos", "debito", "débito", "1"}
INCOME_WORDS = {"receita", "receitas", "entrada", "entradas", "ganho", "ganhos", "credito", "crédito", "2"}

QUESTIONS = SLOT_QUESTIONS


def get_wizard(session: dict) -> dict | None:
    return session.get(WIZARD_KEY)


def clear_wizard(session: dict) -> None:
    session.pop(WIZARD_KEY, None)


def mark_login_prompt(session: dict) -> None:
    session[PROMPT_FLAG] = True


def consume_login_prompt(session: dict) -> bool:
    return bool(session.pop(PROMPT_FLAG, False))


def start_wizard(session: dict, *, source_message: str | None = None) -> None:
    session[WIZARD_KEY] = {
        "tx_type": None,
        "status": None,
        "amount": None,
        "description": None,
        "account_name": None,
        "category_name": None,
        "competence_date": None,
        "due_date": None,
        "payment_date": None,
        "transaction_date": None,
        "source_message": source_message,
        "suggested_category": None,
    }


def begin_login_prompt(session: dict) -> AgentResponse:
    start_wizard(session)
    return AgentResponse(
        message=(
            "Olá! Quer lançar uma **despesa** ou uma **receita** agora?\n\n"
            "Responda com *despesa* ou *receita*."
        ),
        suggestions=for_transaction_wizard_field("tx_type", None, None, {}),
        source="wizard",
    )


def _parse_tx_type(message: str) -> str | None:
    lower = message.lower().strip()

    if lower in EXPENSE_WORDS:
        return "expense"
    if lower in INCOME_WORDS:
        return "income"

    amount = parse_amount(message)
    if amount:
        if any(h in lower for h in ("gastei", "paguei", "comprei", "gasto")):
            return "expense"
        if any(h in lower for h in ("recebi", "ganhei", "entrada")):
            return "income"

    if len(lower.split()) <= 3:
        if "despesa" in lower and "receita" not in lower:
            return "expense"
        if "receita" in lower and "despesa" not in lower:
            return "income"

    return None


def _next_field(wizard: dict) -> str | None:
    return _next_slot(wizard)


def _fill_field(wizard: dict, field: str, message: str) -> str | None:
    if field == "tx_type":
        tx_type = _parse_tx_type(message)
        if not tx_type:
            return "Responda com *despesa* ou *receita*."
        wizard["tx_type"] = tx_type
        return None

    if field == "status":
        status = parse_status_answer(message)
        if not status:
            return "Responda com *realizado* ou *previsto*."
        wizard["status"] = status
        return None

    if field == "amount":
        amount = parse_amount(message)
        if not amount:
            return "Valor inválido. Informe como '45,90' ou '100'."
        wizard["amount"] = amount
        return None

    if field == "description":
        relative = parse_date(message)
        if relative:
            wizard["transaction_date"] = relative.isoformat()
        desc = strip_relative_date_tokens(message.strip())
        if len(desc) < 2:
            if relative:
                return None
            return "Informe uma descrição com pelo menos 2 caracteres."
        wizard["description"] = correct_movement_description(desc)[:255]
        return None

    return "Campo desconhecido."


def _confirmation_response(wizard: dict) -> AgentResponse:
    tool_call = _tool_call_from_wizard(wizard)
    return AgentResponse(
        message=format_pending_confirmation(tool_call),
        needs_confirmation=True,
        pending_action=tool_call.model_dump(),
        tool_used=tool_call.tool,
        source="wizard",
    )


def is_slot_answer(
    message: str,
    field: str,
    *,
    db: Session | None = None,
    user_id: int | None = None,
    wizard: dict | None = None,
) -> bool:
    if is_complex_message(message):
        return False

    if field == "tx_type":
        return _parse_tx_type(message) is not None
    if field == "status":
        return parse_status_answer(message) is not None
    if field in DATE_SLOTS:
        return parse_slot_date(message, wizard) is not None and is_short_slot_message(
            message, max_words=8
        )
    if field == "amount":
        return parse_amount(message) is not None
    if field == "description":
        text = message.strip()
        if is_relative_date_message(text):
            return False
        return len(text) >= 2 and is_short_slot_message(text, max_words=8)
    if field == "account_name" and db is not None and user_id is not None:
        choices = list_active_account_names(db, user_id)
        return parse_account_answer(message, choices) is not None
    if field == "category_name" and db is not None and user_id is not None and wizard:
        tx_type = wizard.get("tx_type") or "expense"
        choices = list_category_names(db, user_id, tx_type)
        return (
            parse_category_answer(message, choices, wizard.get("suggested_category"))
            is not None
        )
    return False


def get_wizard_context(session: dict) -> str | None:
    wizard = get_wizard(session)
    if not wizard:
        return None
    field = _next_field(wizard)
    if not field:
        return "Wizard de lancamento aguardando confirmacao"
    labels = {
        "tx_type": "tipo (despesa ou receita)",
        "status": "status (realizado ou previsto)",
        "competence_date": "data de competencia",
        "due_date": "data de vencimento",
        "payment_date": "data da realizacao",
        "amount": "valor",
        "description": "descricao",
        "account_name": "conta bancaria",
        "category_name": "categoria",
    }
    return f"Wizard de lancamento aguardando: {labels.get(field, field)}"


def _append_source_message(wizard: dict, message: str) -> None:
    if wizard.get("source_message"):
        wizard["source_message"] = f"{wizard['source_message']} {message}".strip()
    else:
        wizard["source_message"] = message


def _response_for_relative_date(
    session: dict,
    wizard: dict,
    message: str,
    *,
    db: Session | None = None,
    user_id: int | None = None,
) -> AgentResponse:
    relative = parse_date(message)
    assert relative is not None
    wizard["transaction_date"] = relative.isoformat()
    _append_source_message(wizard, message)
    session[WIZARD_KEY] = wizard

    next_field = _next_field(wizard)
    date_label = relative.strftime("%d/%m/%Y")
    if next_field is None:
        return _confirmation_response(wizard)

    if next_field in {"account_name", "category_name"} and db is not None and user_id is not None:
        question = _question_for_slot(db, user_id, wizard, next_field)
        suggestions = for_transaction_wizard_field(next_field, db, user_id, wizard)
    else:
        question = QUESTIONS.get(next_field, "")
        suggestions = for_transaction_wizard_field(next_field, None, None, wizard)

    return AgentResponse(
        message=f"Data anotada: *{date_label}*.\n\n{question}",
        suggestions=suggestions,
        source="wizard",
    )


def try_process_transaction_wizard(
    session: dict, message: str, db=None, user_id: int | None = None
) -> AgentResponse | None:
    wizard = get_wizard(session)
    if not wizard:
        return None

    if message.strip().lower() in CANCEL_WORDS:
        clear_wizard(session)
        return AgentResponse(
            message="Lançamento cancelado.",
            source="wizard",
        )

    next_field = _next_field(wizard)
    if next_field is None:
        lower = message.strip().lower()
        if lower in {"sim", "s", "ok", "confirmo", "isso", "essa", "esse"}:
            return _confirmation_response(wizard)
        clear_wizard(session)
        return None

    if count_amounts(message) >= 2 and next_field in {
        "tx_type",
        "status",
        "amount",
        "description",
        *DATE_SLOTS,
    }:
        return None

    if next_field not in DATE_SLOTS and is_relative_date_message(message):
        return _response_for_relative_date(
            session, wizard, message, db=db, user_id=user_id
        )

    if not is_slot_answer(
        message, next_field, db=db, user_id=user_id, wizard=wizard
    ):
        clear_wizard(session)
        return None

    if next_field in {"status", "account_name", "category_name"} | DATE_SLOTS:
        if next_field in {"account_name", "category_name"} and (db is None or user_id is None):
            return AgentResponse(
                message=_question_for_slot(db, user_id, wizard, next_field),
                suggestions=for_transaction_wizard_field(
                    next_field, db, user_id, wizard
                ),
                source="wizard",
            )
        if next_field == "status":
            error = _fill_field(wizard, "status", message)
            if error:
                session[WIZARD_KEY] = wizard
                return AgentResponse(
                    message=error,
                    suggestions=for_transaction_wizard_field("status", None, None, wizard),
                    source="wizard",
                )
        else:
            error = fill_slot(wizard, next_field, message, db, user_id)
            if error:
                session[WIZARD_KEY] = wizard
                return AgentResponse(message=error, source="wizard")
        session[WIZARD_KEY] = wizard
        apply_inferred_dates(wizard)
        session[WIZARD_KEY] = wizard
        if db is not None and user_id is not None:
            _apply_inference(db, user_id, wizard)
            session[WIZARD_KEY] = wizard
        remaining = _next_field(wizard)
        if remaining is None:
            return _confirmation_response(wizard)
        if remaining in {"account_name", "category_name"} and db is not None and user_id is not None:
            return AgentResponse(
                message=_question_for_slot(db, user_id, wizard, remaining),
                suggestions=for_transaction_wizard_field(remaining, db, user_id, wizard),
                source="wizard",
            )
        return AgentResponse(
            message=_question_for_slot(db, user_id, wizard, remaining)
            if remaining in {"account_name", "category_name"} and db is not None and user_id is not None
            else QUESTIONS.get(remaining, ""),
            suggestions=for_transaction_wizard_field(remaining, db, user_id, wizard),
            source="wizard",
        )

    error = _fill_field(wizard, next_field, message)
    if error:
        session[WIZARD_KEY] = wizard
        return AgentResponse(message=error, source="wizard")

    if next_field == "description" and not wizard.get("description"):
        session[WIZARD_KEY] = wizard
        _append_source_message(wizard, message)
        session[WIZARD_KEY] = wizard
        if db is not None and user_id is not None:
            _apply_inference(db, user_id, wizard)
            session[WIZARD_KEY] = wizard
        return AgentResponse(
            message=QUESTIONS["description"],
            suggestions=for_transaction_wizard_field("description", None, None, wizard),
            source="wizard",
        )

    session[WIZARD_KEY] = wizard
    _append_source_message(wizard, message)

    if db is not None and user_id is not None:
        _apply_inference(db, user_id, wizard)
        session[WIZARD_KEY] = wizard

    remaining = _next_field(wizard)
    if remaining is None:
        return _confirmation_response(wizard)

    if remaining in {"account_name", "category_name"} and db is not None and user_id is not None:
        return AgentResponse(
            message=_question_for_slot(db, user_id, wizard, remaining),
            suggestions=for_transaction_wizard_field(remaining, db, user_id, wizard),
            source="wizard",
        )

    return AgentResponse(
        message=QUESTIONS.get(remaining, ""),
        suggestions=for_transaction_wizard_field(remaining, None, None, wizard)
        if remaining
        else None,
        source="wizard",
    )
