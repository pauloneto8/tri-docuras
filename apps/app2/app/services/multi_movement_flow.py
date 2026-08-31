"""Fluxo de confirmação e gravação de vários lançamentos numa mensagem."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.schemas import AgentResponse, RegisterExpenseInput, RegisterIncomeInput, ToolCall
from app.services import finance
from app.services.multi_movements import (
    PENDING_MOVEMENTS_KEY,
    ParsedMovement,
    clear_pending_movements,
    get_pending_movements,
    parse_multi_movements,
)
from app.services.agent_suggestions import for_multi_slot
from app.services.tools import format_tool_result
from app.services.transaction_slots import (
    infer_account_name,
    infer_category_name,
    list_active_account_names,
    list_category_names,
    parse_account_answer,
    parse_category_answer,
)


def _tool_for_movement(item: dict) -> str:
    return "register_income" if item.get("tx_type") == "income" else "register_expense"


def _apply_inference(db: Session, user_id: int, pending: dict) -> None:
    message = pending.get("source_message") or ""
    account = pending.get("account_name")
    if not account:
        inferred = infer_account_name(db, user_id, message, None)
        if inferred:
            pending["account_name"] = inferred
            account = inferred

    for item in pending.get("items", []):
        if account and not item.get("account_name"):
            item["account_name"] = account
        if not item.get("category_name") and item.get("description"):
            inferred_cat = infer_category_name(
                db,
                user_id,
                item["description"],
                item.get("tx_type", "expense"),
            )
            if inferred_cat:
                item["category_name"] = inferred_cat


def _missing_slot(pending: dict) -> tuple[str, int] | None:
    if not pending.get("account_name"):
        return ("account_name", -1)
    for idx, item in enumerate(pending.get("items", [])):
        if not item.get("category_name"):
            return ("category_name", idx)
    return None


def _question_for_slot(
    db: Session, user_id: int, pending: dict, slot: str, item_idx: int
) -> str:
    if slot == "account_name":
        names = list_active_account_names(db, user_id)
        joined = ", ".join(names) if names else "nenhuma"
        count = len(pending.get("items", []))
        return (
            f"Vou registrar {count} lançamentos. Em qual conta? "
            f"Você tem: {joined}."
        )
    if slot == "category_name" and item_idx >= 0:
        item = pending["items"][item_idx]
        tx_type = item.get("tx_type", "expense")
        names = list_category_names(db, user_id, tx_type)
        joined = ", ".join(names) if names else "nenhuma"
        return (
            f"Qual categoria para '{item['description']}' (R$ {item['amount']})? "
            f"Opções: {joined}."
        )
    return "Informe o dado solicitado."


def _format_batch_confirmation(pending: dict) -> str:
    items = pending.get("items", [])
    tx_type = items[0].get("tx_type", "expense") if items else "expense"
    label = "despesas" if tx_type == "expense" else "receitas"
    lines = [f"Confirmar {len(items)} {label}:"]
    for i, item in enumerate(items, 1):
        lines.append(
            f"{i}. R$ {item['amount']} — {item['description']}"
            f" ({item.get('category_name') or 'sem categoria'})"
        )
    lines.append(f"Conta: {pending.get('account_name')}")
    tx_date = items[0].get("transaction_date") if items else None
    lines.append(f"Data: {tx_date or 'hoje'}")
    lines.append("Clique em Confirmar para registrar todos.")
    return "\n".join(lines)


def _pending_to_batch_action(pending: dict) -> dict:
    items = []
    for item in pending.get("items", []):
        tool = _tool_for_movement(item)
        args = {
            "amount": item["amount"],
            "description": item["description"],
            "account_name": item.get("account_name") or pending.get("account_name"),
            "category_name": item.get("category_name"),
        }
        if item.get("transaction_date"):
            args["transaction_date"] = item["transaction_date"]
        items.append({"tool": tool, "arguments": args})
    return {"batch": True, "items": items}


def begin_multi_movement_flow(
    db: Session,
    user_id: int,
    session: dict,
    movements: list[ParsedMovement],
    source_message: str,
) -> AgentResponse:
    from app.services.transaction_wizard import clear_wizard as clear_tx_wizard

    clear_tx_wizard(session)
    pending = {
        "items": [m.to_dict() for m in movements],
        "account_name": None,
        "source_message": source_message,
    }
    _apply_inference(db, user_id, pending)
    session[PENDING_MOVEMENTS_KEY] = pending

    missing = _missing_slot(pending)
    if missing:
        slot, idx = missing
        return AgentResponse(
            message=_question_for_slot(db, user_id, pending, slot, idx),
            suggestions=for_multi_slot(slot, db, user_id, pending, idx),
            source="multi",
        )

    action = _pending_to_batch_action(pending)
    clear_pending_movements(session)
    return AgentResponse(
        message=_format_batch_confirmation(pending),
        needs_confirmation=True,
        pending_action=action,
        tool_used="register_expense",
        source="multi",
    )


def try_process_multi_movement_flow(
    session: dict,
    message: str,
    db: Session,
    user_id: int,
) -> AgentResponse | None:
    pending = get_pending_movements(session)
    if not pending:
        return None

    if message.strip().lower() in {"cancelar", "desistir", "abortar", "sair", "não", "nao"}:
        clear_pending_movements(session)
        return AgentResponse(message="Lançamentos cancelados.", source="multi")

    missing = _missing_slot(pending)
    if not missing:
        action = _pending_to_batch_action(pending)
        clear_pending_movements(session)
        return AgentResponse(
            message=_format_batch_confirmation(pending),
            needs_confirmation=True,
            pending_action=action,
            tool_used="register_expense",
            source="multi",
        )

    slot, item_idx = missing
    if slot == "account_name":
        choices = list_active_account_names(db, user_id)
        parsed = parse_account_answer(message, choices)
        if not parsed:
            return AgentResponse(
                message=f"Conta inválida. Escolha uma das opções: {', '.join(choices)}.",
                suggestions=for_multi_slot("account_name", db, user_id, pending, -1),
                source="multi",
            )
        pending["account_name"] = parsed
        for item in pending["items"]:
            item["account_name"] = parsed
    elif slot == "category_name" and item_idx >= 0:
        item = pending["items"][item_idx]
        tx_type = item.get("tx_type", "expense")
        choices = list_category_names(db, user_id, tx_type)
        parsed = parse_category_answer(message, choices)
        if not parsed:
            return AgentResponse(
                message=f"Categoria inválida. Escolha uma das opções: {', '.join(choices)}.",
                suggestions=for_multi_slot("category_name", db, user_id, pending, item_idx),
                source="multi",
            )
        item["category_name"] = parsed

    session[PENDING_MOVEMENTS_KEY] = pending
    _apply_inference(db, user_id, pending)

    missing = _missing_slot(pending)
    if missing:
        slot, idx = missing
        return AgentResponse(
            message=_question_for_slot(db, user_id, pending, slot, idx),
            suggestions=for_multi_slot(slot, db, user_id, pending, idx),
            source="multi",
        )

    action = _pending_to_batch_action(pending)
    clear_pending_movements(session)
    return AgentResponse(
        message=_format_batch_confirmation(pending),
        needs_confirmation=True,
        pending_action=action,
        tool_used="register_expense",
        source="multi",
    )


def execute_batch_movements(db: Session, user_id: int, batch_action: dict) -> str:
    results: list[str] = []
    for entry in batch_action.get("items", []):
        tool = entry["tool"]
        args = dict(entry["arguments"])
        if args.get("transaction_date") and isinstance(args["transaction_date"], str):
            args["transaction_date"] = date.fromisoformat(args["transaction_date"])
        if tool == "register_expense":
            payload = RegisterExpenseInput(**args)
            result = finance.register_expense(db, user_id, payload)
            results.append(format_tool_result("register_expense", result))
        elif tool == "register_income":
            payload = RegisterIncomeInput(**args)
            result = finance.register_income(db, user_id, payload)
            results.append(format_tool_result("register_income", result))
    if not results:
        raise ValueError("Nenhum lançamento para registrar.")
    header = f"{len(results)} lançamentos registrados:\n"
    return header + "\n".join(f"• {line}" for line in results)


def try_begin_from_message(
    db: Session,
    user_id: int,
    session: dict,
    message: str,
) -> AgentResponse | None:
    from app.services.transaction_slots import DATE_SLOTS, RECURRENCE_SLOTS
    from app.services.transaction_wizard import get_wizard as get_tx_wizard
    from app.services.transaction_wizard import _next_field

    wizard = get_tx_wizard(session)
    if wizard:
        field = _next_field(wizard)
        if field in {"account_name", "category_name"} | DATE_SLOTS | RECURRENCE_SLOTS:
            return None
    tx_type_hint = wizard.get("tx_type") if wizard else None
    movements = parse_multi_movements(message, tx_type_hint=tx_type_hint)
    if not movements:
        return None
    return begin_multi_movement_flow(db, user_id, session, movements, message)
