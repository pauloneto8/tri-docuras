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
    PAYMENT_SOURCE_SLOTS,
    SLOT_QUESTIONS,
    WIZARD_KEY,
    _apply_inference,
    _next_slot,
    _question_for_slot,
    _tool_call_from_wizard,
    apply_inferred_dates,
    fill_slot,
    list_active_account_names,
    list_active_card_names,
    list_category_names,
    parse_account_answer,
    parse_category_answer,
    parse_payment_source_answer,
    parse_slot_date,
    parse_status_answer,
    refresh_wizard_payment_context,
)
from app.services.wizard_slots import is_complex_message, is_short_slot_message

PROMPT_FLAG = "prompt_transaction_on_login"
PAUSED_WIZARD_KEY = "paused_transaction_wizard"

CANCEL_WORDS = {"cancelar", "desistir", "abortar", "sair", "não", "nao"}
EXPENSE_WORDS = {"despesa", "despesas", "gasto", "gastos", "debito", "débito", "1"}
INCOME_WORDS = {"receita", "receitas", "entrada", "entradas", "ganho", "ganhos", "credito", "crédito", "2"}
NEW_CATEGORY_WORDS = {"nova categoria", "nova", "criar categoria", "cadastrar categoria"}

QUESTIONS = SLOT_QUESTIONS


def get_wizard(session: dict) -> dict | None:
    return session.get(WIZARD_KEY)


def clear_wizard(session: dict) -> None:
    session.pop(WIZARD_KEY, None)


def get_paused_wizard(session: dict) -> dict | None:
    return session.get(PAUSED_WIZARD_KEY)


def clear_paused_wizard(session: dict) -> None:
    session.pop(PAUSED_WIZARD_KEY, None)


def pause_transaction_for_category(session: dict, wizard: dict) -> None:
    """Guarda o lançamento em andamento enquanto cadastra categoria nova."""
    session[PAUSED_WIZARD_KEY] = dict(wizard)
    session.pop(WIZARD_KEY, None)


def resume_paused_transaction_after_category(
    session: dict, *, category_name: str
) -> AgentResponse | None:
    """Retoma o lançamento pausado após criar categoria e vai para confirmação."""
    paused = get_paused_wizard(session)
    if not paused:
        return None
    clear_paused_wizard(session)
    paused["category_name"] = category_name
    session[WIZARD_KEY] = paused
    confirmation = _confirmation_response(paused)
    confirmation.message = (
        f"Categoria '{category_name}' cadastrada. Seguindo com o lançamento.\n\n"
        f"{confirmation.message}"
    )
    return confirmation


def restore_paused_transaction_on_category_cancel(
    session: dict,
) -> AgentResponse | None:
    """Se o usuário cancelar o cadastro de categoria, volta ao slot de categoria."""
    paused = get_paused_wizard(session)
    if not paused:
        return None
    clear_paused_wizard(session)
    session[WIZARD_KEY] = paused
    return AgentResponse(
        message=(
            "Cadastro de categoria cancelado. "
            "Qual categoria usar no lançamento? Informe um nome existente "
            "ou digite o nome de uma nova."
        ),
        suggestions=for_transaction_wizard_field(
            "category_name", None, None, paused
        ),
        source="wizard",
    )


def _looks_like_new_category_name(message: str) -> bool:
    from app.services.text_correction import correct_category_name

    lower = message.strip().lower()
    if lower in NEW_CATEGORY_WORDS or lower.startswith("nova "):
        return True
    if is_complex_message(message):
        return False
    name = correct_category_name(message.strip())
    return len(name) >= 2 and is_short_slot_message(name, max_words=6)


def _begin_category_from_transaction(
    session: dict,
    wizard: dict,
    message: str,
) -> AgentResponse:
    from app.services.category_wizard import begin_category_wizard
    from app.services.text_correction import correct_category_name

    pause_transaction_for_category(session, wizard)
    lower = message.strip().lower()
    initial: dict = {"type": wizard.get("tx_type") or "expense"}
    if lower not in NEW_CATEGORY_WORDS and not lower.startswith("nova categoria"):
        name = correct_category_name(message.strip())
        if len(name) >= 2:
            initial["name"] = name
    return begin_category_wizard(session, message, initial=initial)


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
        "card_name": None,
        "category_name": None,
        "competence_date": None,
        "due_date": None,
        "payment_date": None,
        "transaction_date": None,
        "payment_source": None,
        "payment_on_card": False,
        "has_credit_cards": False,
        "payment_mode": None,
        "is_recurring": None,
        "frequency": None,
        "recurrence_end_date": None,
        "recurrence_end_asked": False,
        "installment_count": None,
        "installment_interval": None,
        "installment_start_index": None,
        "installment_amount_basis": None,
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


def _message_for_remaining(
    db: Session | None,
    user_id: int | None,
    wizard: dict,
    remaining: str,
) -> str:
    if db is not None and user_id is not None:
        return _question_for_slot(db, user_id, wizard, remaining)
    return QUESTIONS.get(remaining, "")


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
        return parse_slot_date(message, wizard, slot=field) is not None and is_short_slot_message(
            message, max_words=8
        )
    if field == "payment_mode":
        from app.services.transaction_slots import parse_payment_mode_answer

        return parse_payment_mode_answer(message) is not None
    if field == "is_recurring":
        from app.services.transaction_slots import parse_is_recurring_answer

        return parse_is_recurring_answer(message) is not None
    if field == "installment_count":
        from app.services.installments import parse_installment_count

        return parse_installment_count(message) is not None
    if field == "installment_interval":
        from app.services.installments import parse_installment_interval

        return parse_installment_interval(message) is not None
    if field == "installment_start_index":
        from app.services.installments import parse_installment_start_index

        max_count = int((wizard or {}).get("installment_count") or 360)
        return parse_installment_start_index(message, max_count) is not None
    if field == "installment_amount_basis":
        from app.services.transaction_slots import parse_installment_amount_basis

        return parse_installment_amount_basis(message) is not None
    if field == "frequency":
        from app.services.recurrence import parse_frequency

        return parse_frequency(message) is not None
    if field == "recurrence_end_date":
        lower = message.strip().lower()
        if lower in {"não", "nao", "n", "no", "sem", "nunca"}:
            return True
        return parse_slot_date(message, wizard) is not None
    if field == "payment_source":
        return parse_payment_source_answer(message) is not None
    if field == "card_name" and db is not None and user_id is not None:
        choices = list_active_card_names(db, user_id)
        return parse_account_answer(message, choices) is not None
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
        "payment_source": "forma de pagamento (cartao ou conta)",
        "card_name": "cartao de credito",
        "competence_date": "data de competencia",
        "due_date": "data de vencimento",
        "payment_date": "data da realizacao",
        "payment_mode": "tipo do lancamento (unico, fixo ou parcelado)",
        "is_recurring": "se e lancamento fixo",
        "frequency": "frequencia do lancamento fixo",
        "recurrence_end_date": "data de termino da serie",
        "installment_count": "numero de parcelas",
        "installment_interval": "intervalo das parcelas",
        "installment_start_index": "parcela atual do parcelamento",
        "installment_amount_basis": "valor total ou valor da parcela",
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

    next_field = _next_field(wizard)
    if next_field is None:
        lower = message.strip().lower()
        if lower in {"sim", "s", "ok", "confirmo", "isso", "essa", "esse"}:
            return _confirmation_response(wizard)
        clear_wizard(session)
        return None

    lower_msg = message.strip().lower()
    if lower_msg in CANCEL_WORDS:
        from app.services.transaction_slots import INSTALLMENT_SLOTS

        if lower_msg in {"não", "nao"} and next_field in {
            "payment_mode",
            "is_recurring",
            "recurrence_end_date",
        } | INSTALLMENT_SLOTS:
            pass
        else:
            clear_wizard(session)
            return AgentResponse(
                message="Lançamento cancelado.",
                source="wizard",
            )

    if count_amounts(message) >= 2 and next_field in {
        "tx_type",
        "status",
        "amount",
        "description",
    }:
        return None

    if next_field not in DATE_SLOTS and is_relative_date_message(message):
        return _response_for_relative_date(
            session, wizard, message, db=db, user_id=user_id
        )

    if not is_slot_answer(
        message, next_field, db=db, user_id=user_id, wizard=wizard
    ):
        if (
            next_field == "category_name"
            and db is not None
            and user_id is not None
            and _looks_like_new_category_name(message)
        ):
            return _begin_category_from_transaction(session, wizard, message)
        clear_wizard(session)
        return None

    from app.services.transaction_slots import INSTALLMENT_SLOTS, MODE_SLOTS, RECURRENCE_SLOTS

    slot_fields = (
        {"status", "account_name", "category_name", "card_name"}
        | DATE_SLOTS
        | MODE_SLOTS
        | PAYMENT_SOURCE_SLOTS
        | RECURRENCE_SLOTS
        | INSTALLMENT_SLOTS
    )

    if next_field in slot_fields:
        if next_field in MODE_SLOTS | RECURRENCE_SLOTS | INSTALLMENT_SLOTS | PAYMENT_SOURCE_SLOTS:
            error = fill_slot(wizard, next_field, message, db, user_id)
            if error:
                return AgentResponse(
                    message=error,
                    suggestions=for_transaction_wizard_field(
                        next_field, db, user_id, wizard
                    ),
                    source="wizard",
                )
            session[WIZARD_KEY] = wizard
            if db is not None and user_id is not None:
                _apply_inference(db, user_id, wizard)
                refresh_wizard_payment_context(db, user_id, wizard)
            session[WIZARD_KEY] = wizard
            remaining = _next_field(wizard)
            if remaining is None:
                return _confirmation_response(wizard)
            return AgentResponse(
                message=_question_for_slot(db, user_id, wizard, remaining),
                suggestions=for_transaction_wizard_field(
                    remaining, db, user_id, wizard
                ),
                source="wizard",
            )

        if next_field in {"account_name", "category_name", "card_name"} and (
            db is None or user_id is None
        ):
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
            refresh_wizard_payment_context(db, user_id, wizard)
            session[WIZARD_KEY] = wizard
        remaining = _next_field(wizard)
        if remaining is None:
            return _confirmation_response(wizard)
        if remaining in {"account_name", "category_name", "card_name"} and db is not None and user_id is not None:
            return AgentResponse(
                message=_question_for_slot(db, user_id, wizard, remaining),
                suggestions=for_transaction_wizard_field(remaining, db, user_id, wizard),
                source="wizard",
            )
        return AgentResponse(
            message=_message_for_remaining(db, user_id, wizard, remaining),
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
        refresh_wizard_payment_context(db, user_id, wizard)
        session[WIZARD_KEY] = wizard

    remaining = _next_field(wizard)
    if remaining is None:
        return _confirmation_response(wizard)

    if remaining in {"account_name", "category_name", "card_name"} and db is not None and user_id is not None:
        return AgentResponse(
            message=_question_for_slot(db, user_id, wizard, remaining),
            suggestions=for_transaction_wizard_field(remaining, db, user_id, wizard),
            source="wizard",
        )

    return AgentResponse(
        message=_message_for_remaining(db, user_id, wizard, remaining),
        suggestions=for_transaction_wizard_field(remaining, db, user_id, wizard)
        if remaining
        else None,
        source="wizard",
    )
