"""Pergunta de escopo ao editar parcela com parcelas seguintes (agente)."""

from __future__ import annotations

from app.schemas import AgentResponse, ToolCall
from app.services.agent_state import is_cancel_message
from app.services.installments import (
    count_subsequent_installments,
    parse_installment_scope_answer,
)
from app.services.tools import format_pending_confirmation

PENDING_KEY = "pending_installment_scope_update"


def clear_pending_installment_scope(session: dict) -> None:
    session.pop(PENDING_KEY, None)


def try_process_installment_scope(
    session: dict, message: str, *, db, user_id: int
) -> AgentResponse | None:
    pending = session.get(PENDING_KEY)
    if not pending:
        return None

    if is_cancel_message(message, session):
        clear_pending_installment_scope(session)
        return AgentResponse(
            message="Atualização cancelada.",
            clear_wizard=True,
            source="wizard",
        )

    scope = parse_installment_scope_answer(message)
    if not scope:
        subsequent = pending.get("subsequent_count") or 0
        return AgentResponse(
            message=(
                "Responda se deseja atualizar *só esta parcela* ou "
                f"*esta e as {subsequent} seguintes*."
            ),
            suggestions=["Só esta parcela", "Esta e as seguintes"],
            source="wizard",
        )

    args = dict(pending.get("arguments") or {})
    args["installment_scope"] = scope
    tool_call = ToolCall(tool="update_transaction", arguments=args)
    clear_pending_installment_scope(session)
    return AgentResponse(
        message=format_pending_confirmation(tool_call),
        needs_confirmation=True,
        pending_action=tool_call.model_dump(),
        tool_used="update_transaction",
        source="wizard",
    )


def maybe_ask_installment_scope(
    db,
    user_id: int,
    session: dict,
    tool_call: ToolCall,
    *,
    source: str | None = None,
) -> AgentResponse | None:
    """Se o update afeta parcela com seguintes e sem escopo, pergunta."""
    if tool_call.tool != "update_transaction":
        return None
    args = dict(tool_call.arguments or {})
    if args.get("installment_scope") in {"this", "subsequent"}:
        return None

    from app.services import finance

    tx = finance.find_transaction(
        db,
        user_id,
        transaction_id=args.get("transaction_id"),
        description=None,
        amount=args.get("amount") if not args.get("transaction_id") else None,
    )
    # Sem id/amount: tenta descrição antiga só se amount não identifica
    if not tx and args.get("description") and not args.get("amount"):
        tx = finance.find_transaction(
            db,
            user_id,
            description=args.get("description"),
        )
    if not tx or not tx.installment_plan_id:
        return None

    subsequent = count_subsequent_installments(db, user_id, tx)
    if subsequent <= 0:
        args["installment_scope"] = "this"
        tool_call.arguments = args
        return None

    label = None
    if tx.installment_index and tx.installment_plan:
        from app.services.installments import format_installment_label

        label = format_installment_label(
            tx.installment_index,
            tx.installment_plan.installment_count,
            tx.installment_plan.interval,
        )

    session[PENDING_KEY] = {
        "arguments": args,
        "subsequent_count": subsequent,
        "transaction_id": tx.id,
    }
    # Garante id para a confirmação seguinte
    args["transaction_id"] = tx.id
    session[PENDING_KEY]["arguments"] = args

    parcel_bit = f" ({label})" if label else ""
    return AgentResponse(
        message=(
            f"Este lançamento é a parcela{parcel_bit} de um parcelamento e há "
            f"{subsequent} parcela(s) seguinte(s). "
            "Deseja atualizar *só esta parcela* ou *esta e as seguintes*?"
        ),
        suggestions=["Só esta parcela", "Esta e as seguintes"],
        source=source or "wizard",
        tool_used="update_transaction",
    )
