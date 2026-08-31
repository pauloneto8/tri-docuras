"""Slots para realizar lançamentos previstos no assistente."""

import re

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.schemas import ToolCall
from app.services.agent_suggestions import for_realize_planned_field
from app.services.finance import find_transaction, find_transactions, list_transactions
from app.services.transaction_slots import (
    infer_account_name,
    list_active_account_names,
    parse_account_answer,
    parse_slot_date,
)
from app.services.tools import parse_amount
from app.timezone import local_today

WIZARD_KEY = "realize_planned_wizard"

QUESTIONS = {
    "planned": "Qual previsão deseja realizar?",
    "payment_date": "Qual a data de pagamento?",
    "same_account": "Será na mesma conta do previsto?",
    "account_name": "Em qual conta será realizado?",
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


def _pending_planned_labels(db: Session, user_id: int) -> list[tuple[int, str]]:
    from app.schemas import ListTransactionsInput

    rows = list_transactions(
        db, user_id, ListTransactionsInput(limit=20, status="planned")
    )
    return [
        (tx["id"], f"{tx['description']} (R$ {tx['amount']})")
        for tx in rows
        if not tx.get("is_realized")
    ]


def _resolve_planned_tx(
    db: Session,
    user_id: int,
    *,
    planned_id: int | None,
    description: str | None,
    message: str,
) -> tuple[object | None, str | None]:
    if planned_id is not None:
        tx = find_transaction(db, user_id, transaction_id=planned_id)
        if tx and tx.status == "planned":
            return tx, None
        return None, "Previsão não encontrada."

    hint = (description or message or "").strip()
    if not hint:
        return None, None

    candidates = [
        tx
        for tx in find_transactions(db, user_id, description=hint, limit=20)
        if tx.status == "planned"
    ]
    if len(candidates) == 1:
        return candidates[0], None
    if len(candidates) > 1:
        return None, None

    for word in re.findall(r"\w+", hint.lower()):
        if len(word) < 4:
            continue
        scoped = [
            tx
            for tx in find_transactions(db, user_id, description=word, limit=20)
            if tx.status == "planned"
        ]
        if len(scoped) == 1:
            return scoped[0], None

    return None, "Previsão não encontrada." if hint else None, None


def _parse_same_account(message: str) -> bool | None:
    lower = message.strip().lower()
    if lower in {"sim", "s", "yes", "mesma", "mesma conta", "igual"}:
        return True
    if lower in {"não", "nao", "n", "no", "outra", "outra conta", "diferente"}:
        return False
    return None


def _start_wizard(session: dict, tool_call: ToolCall) -> dict:
    data = {
        "planned_id": tool_call.arguments.get("planned_id"),
        "description": tool_call.arguments.get("description"),
        "planned_account_name": None,
        "payment_date": tool_call.arguments.get("payment_date")
        or tool_call.arguments.get("transaction_date"),
        "amount": tool_call.arguments.get("amount"),
        "same_account": None,
        "account_name": tool_call.arguments.get("account_name"),
    }
    session[WIZARD_KEY] = data
    return data


def _next_field(wizard: dict) -> str | None:
    if not wizard.get("planned_id"):
        return "planned"
    if not wizard.get("payment_date"):
        return "payment_date"
    if wizard.get("same_account") is None:
        return "same_account"
    if wizard.get("same_account") is False and not wizard.get("account_name"):
        return "account_name"
    return None


def _wizard_to_tool_call(wizard: dict) -> ToolCall:
    args: dict = {"planned_id": wizard["planned_id"]}
    if wizard.get("amount"):
        args["amount"] = wizard["amount"]
    if wizard.get("payment_date"):
        args["payment_date"] = wizard["payment_date"]
    account_name = wizard.get("account_name")
    if account_name:
        args["account_name"] = account_name
    return ToolCall(tool="realize_planned", arguments=args)


def _question_for_field(field: str, wizard: dict) -> str:
    if field == "same_account" and wizard.get("planned_account_name"):
        return (
            f"Será na mesma conta do previsto ({wizard['planned_account_name']})?"
        )
    return QUESTIONS[field]


def ensure_realize_planned_slots(
    db: Session,
    user_id: int,
    session: dict,
    tool_call: ToolCall,
    message: str,
) -> SlotResult:
    wizard = get_wizard(session) or _start_wizard(session, tool_call)

    if not wizard.get("planned_id"):
        planned, _ = _resolve_planned_tx(
            db,
            user_id,
            planned_id=tool_call.arguments.get("planned_id"),
            description=wizard.get("description"),
            message=message,
        )
        if planned:
            wizard["planned_id"] = planned.id
            wizard["planned_account_name"] = planned.account.name if planned.account else None
            if not wizard.get("description"):
                wizard["description"] = planned.description

    if tool_call.arguments.get("amount") and not wizard.get("amount"):
        wizard["amount"] = tool_call.arguments["amount"]
    elif not wizard.get("amount"):
        amount = parse_amount(message.lower())
        if amount:
            wizard["amount"] = amount

    if not wizard.get("payment_date"):
        parsed = parse_slot_date(message)
        if parsed:
            wizard["payment_date"] = parsed

    explicit_account = tool_call.arguments.get("account_name")
    if explicit_account and wizard.get("same_account") is None:
        inferred = infer_account_name(db, user_id, message, explicit_account)
        if inferred and inferred != wizard.get("planned_account_name"):
            wizard["same_account"] = False
            wizard["account_name"] = inferred
        elif inferred and inferred == wizard.get("planned_account_name"):
            wizard["same_account"] = True

    session[WIZARD_KEY] = wizard
    field = _next_field(wizard)
    if field:
        return SlotResult(
            question=_question_for_field(field, wizard),
            suggestions=for_realize_planned_field(field, db, user_id, wizard),
        )

    if wizard.get("same_account") is True:
        wizard["account_name"] = wizard.get("planned_account_name")

    return SlotResult(tool_call=_wizard_to_tool_call(wizard))


def try_process_realize_planned_wizard(
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

    field = _next_field(wizard)
    if field is None:
        return SlotResult(tool_call=_wizard_to_tool_call(wizard))

    if is_cancel_message(message):
        if field != "same_account" or _parse_same_account(message) is None:
            clear_wizard(session)
            return SlotResult(question="Realização cancelada.")

    if field == "planned":
        pending = _pending_planned_labels(db, user_id)
        by_label = {label.lower(): pid for pid, label in pending}
        lower = message.strip().lower()
        matched_id = None
        for pid, label in pending:
            if lower == label.lower() or lower in label.lower():
                matched_id = pid
                break
        if matched_id is None and lower in by_label:
            matched_id = by_label[lower]
        if matched_id is None:
            planned, err = _resolve_planned_tx(
                db,
                user_id,
                planned_id=None,
                description=message,
                message=message,
            )
            if planned:
                matched_id = planned.id
        if matched_id is None:
            return SlotResult(
                question=QUESTIONS["planned"],
                suggestions=for_realize_planned_field("planned", db, user_id, wizard),
            )
        tx = find_transaction(db, user_id, transaction_id=matched_id)
        if not tx or tx.status != "planned":
            return SlotResult(
                question="Previsão não encontrada. Qual previsão deseja realizar?",
                suggestions=for_realize_planned_field("planned", db, user_id, wizard),
            )
        wizard["planned_id"] = tx.id
        wizard["planned_account_name"] = tx.account.name if tx.account else None
        wizard["description"] = tx.description

    elif field == "payment_date":
        parsed = parse_slot_date(message)
        if not parsed:
            return SlotResult(
                question=QUESTIONS["payment_date"],
                suggestions=for_realize_planned_field("payment_date", db, user_id, wizard),
            )
        wizard["payment_date"] = parsed

    elif field == "same_account":
        same = _parse_same_account(message)
        if same is None:
            return SlotResult(
                question=_question_for_field("same_account", wizard),
                suggestions=for_realize_planned_field("same_account", db, user_id, wizard),
            )
        wizard["same_account"] = same
        if same:
            wizard["account_name"] = wizard.get("planned_account_name")

    elif field == "account_name":
        names = list_active_account_names(db, user_id)
        parsed = parse_account_answer(message, names)
        if not parsed:
            return SlotResult(
                question=QUESTIONS["account_name"],
                suggestions=for_realize_planned_field("account_name", db, user_id, wizard),
            )
        wizard["account_name"] = parsed

    session[WIZARD_KEY] = wizard
    remaining = _next_field(wizard)
    if remaining:
        return SlotResult(
            question=_question_for_field(remaining, wizard),
            suggestions=for_realize_planned_field(remaining, db, user_id, wizard),
        )

    if wizard.get("same_account") is True:
        wizard["account_name"] = wizard.get("planned_account_name")

    return SlotResult(tool_call=_wizard_to_tool_call(wizard))
