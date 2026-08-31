"""Slots para transferências entre contas no assistente."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.schemas import ToolCall
from app.services.agent_suggestions import for_transfer_wizard_field
from app.services.transaction_slots import (
    infer_account_name,
    list_active_account_names,
    parse_account_answer,
)
from app.services.tools import parse_amount, parse_date

WIZARD_KEY = "transfer_wizard"

QUESTIONS = {
    "from_account_name": "De qual conta sairá o valor?",
    "to_account_name": "Para qual conta vai o valor?",
    "amount": "Qual o valor da transferência?",
}


@dataclass
class SlotResult:
    tool_call: ToolCall | None = None
    question: str | None = None
    suggestions: list[str] | None = None


def get_wizard(session: dict) -> dict | None:
    return session.get(WIZARD_KEY)


def clear_wizard(session: dict) -> None:
    session.pop(WIZARD_KEY, None)


def _start_wizard(session: dict, tool_call: ToolCall) -> dict:
    data = {
        "amount": tool_call.arguments.get("amount"),
        "from_account_name": tool_call.arguments.get("from_account_name"),
        "to_account_name": tool_call.arguments.get("to_account_name"),
        "description": tool_call.arguments.get("description"),
        "transaction_date": tool_call.arguments.get("transaction_date"),
    }
    session[WIZARD_KEY] = data
    return data


def _next_field(wizard: dict) -> str | None:
    if not wizard.get("amount"):
        return "amount"
    if not wizard.get("from_account_name"):
        return "from_account_name"
    if not wizard.get("to_account_name"):
        return "to_account_name"
    return None


def _wizard_to_tool_call(wizard: dict) -> ToolCall:
    args = {
        "amount": wizard["amount"],
        "from_account_name": wizard["from_account_name"],
        "to_account_name": wizard["to_account_name"],
    }
    if wizard.get("description"):
        args["description"] = wizard["description"]
    if wizard.get("transaction_date"):
        args["transaction_date"] = wizard["transaction_date"]
    return ToolCall(tool="register_transfer", arguments=args)


def ensure_transfer_slots(
    db: Session,
    user_id: int,
    session: dict,
    tool_call: ToolCall,
    message: str,
) -> SlotResult:
    wizard = get_wizard(session) or _start_wizard(session, tool_call)

    if not wizard.get("amount"):
        amount = tool_call.arguments.get("amount") or parse_amount(message.lower())
        if amount:
            wizard["amount"] = amount

    if not wizard.get("from_account_name"):
        explicit = tool_call.arguments.get("from_account_name")
        inferred = infer_account_name(db, user_id, message, explicit)
        if inferred:
            wizard["from_account_name"] = inferred

    if not wizard.get("to_account_name"):
        explicit = tool_call.arguments.get("to_account_name")
        if explicit:
            inferred = infer_account_name(db, user_id, message, explicit)
            if inferred:
                wizard["to_account_name"] = inferred
        elif wizard.get("from_account_name"):
            names = list_active_account_names(db, user_id)
            for name in names:
                if name.lower() in message.lower() and name != wizard.get("from_account_name"):
                    wizard["to_account_name"] = name
                    break

    if tool_call.arguments.get("description") and not wizard.get("description"):
        wizard["description"] = tool_call.arguments["description"]
    if tool_call.arguments.get("transaction_date") and not wizard.get("transaction_date"):
        wizard["transaction_date"] = tool_call.arguments["transaction_date"]
    elif not wizard.get("transaction_date"):
        parsed = parse_date(message.lower())
        if parsed:
            wizard["transaction_date"] = parsed.isoformat()

    session[WIZARD_KEY] = wizard
    field = _next_field(wizard)
    if field:
        return SlotResult(
            question=QUESTIONS[field],
            suggestions=for_transfer_wizard_field(field, db, user_id, wizard),
        )

    if wizard["from_account_name"] == wizard["to_account_name"]:
        wizard["to_account_name"] = None
        session[WIZARD_KEY] = wizard
        return SlotResult(
            question="A conta de origem e destino devem ser diferentes. Para qual conta vai o valor?",
            suggestions=for_transfer_wizard_field("to_account_name", db, user_id, wizard),
        )

    return SlotResult(tool_call=_wizard_to_tool_call(wizard))


def try_process_transfer_wizard(
    session: dict,
    message: str,
    *,
    db: Session,
    user_id: int,
) -> SlotResult | None:
    wizard = get_wizard(session)
    if not wizard:
        return None

    from app.services.agent_state import is_cancel_message

    if is_cancel_message(message):
        clear_wizard(session)
        return SlotResult(question="Transferência cancelada.")

    field = _next_field(wizard)
    if not field:
        return SlotResult(tool_call=_wizard_to_tool_call(wizard))

    if field == "amount":
        amount = parse_amount(message.lower())
        if not amount:
            return SlotResult(
                question="Informe o valor da transferência (ex.: 100,00).",
                suggestions=for_transfer_wizard_field(field, db, user_id, wizard),
            )
        wizard["amount"] = amount
    elif field == "from_account_name":
        names = list_active_account_names(db, user_id)
        parsed = parse_account_answer(message, names)
        if not parsed:
            return SlotResult(
                question=QUESTIONS[field],
                suggestions=for_transfer_wizard_field(field, db, user_id, wizard),
            )
        wizard["from_account_name"] = parsed
    elif field == "to_account_name":
        names = [n for n in list_active_account_names(db, user_id) if n != wizard.get("from_account_name")]
        parsed = parse_account_answer(message, names)
        if not parsed:
            return SlotResult(
                question=QUESTIONS[field],
                suggestions=for_transfer_wizard_field(field, db, user_id, wizard),
            )
        wizard["to_account_name"] = parsed

    session[WIZARD_KEY] = wizard
    remaining = _next_field(wizard)
    if remaining:
        return SlotResult(
            question=QUESTIONS[remaining],
            suggestions=for_transfer_wizard_field(remaining, db, user_id, wizard),
        )
    if wizard["from_account_name"] == wizard["to_account_name"]:
        wizard["to_account_name"] = None
        session[WIZARD_KEY] = wizard
        return SlotResult(
            question="A conta de origem e destino devem ser diferentes. Para qual conta vai o valor?",
            suggestions=for_transfer_wizard_field("to_account_name", db, user_id, wizard),
        )
    return SlotResult(tool_call=_wizard_to_tool_call(wizard))
