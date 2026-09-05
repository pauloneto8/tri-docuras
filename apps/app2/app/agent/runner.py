from pydantic import ValidationError

from app.agent.context import build_intent_context
from app.agent.tool_parse import DEFAULT_UNSUPPORTED_MESSAGE
from app.agent.llm import call_intent_llm
from app.schemas import AgentResponse, ToolCall
from app.services.account_wizard import (
    begin_account_wizard,
    clear_wizard,
    get_wizard,
    try_process_account_wizard,
)
from app.services.card_wizard import (
    begin_card_wizard,
    clear_wizard as clear_card_wizard,
    get_wizard as get_card_wizard,
    try_process_card_wizard,
)
from app.services.category_wizard import (
    begin_category_wizard,
    clear_wizard as clear_category_wizard,
    get_wizard as get_category_wizard,
    try_process_category_wizard,
)
from app.services.pay_invoice_slots import (
    clear_wizard as clear_pay_invoice_wizard,
    get_wizard as get_pay_invoice_wizard,
    try_process_pay_invoice_wizard,
)
from app.services.transfer_slots import (
    clear_wizard as clear_transfer_wizard,
    get_wizard as get_transfer_wizard,
    try_process_transfer_wizard,
)
from app.services.realize_planned_slots import (
    clear_wizard as clear_realize_planned_wizard,
    get_wizard as get_realize_planned_wizard,
    try_process_realize_planned_wizard,
)
from app.services.transaction_wizard import (
    clear_wizard as clear_transaction_wizard,
    get_paused_wizard,
    get_wizard as get_transaction_wizard,
    resume_paused_transaction_after_category,
    try_process_transaction_wizard,
)
from app.services.delete_flow import (
    clear_pending_delete,
    prepare_delete_transaction,
    try_process_pending_delete,
)
from app.services.multi_movement_flow import (
    get_pending_movements,
    try_begin_from_message,
    try_process_multi_movement_flow,
)
from app.services.agent_state import clear_agent_flow_state
from app.services.tools import (
    execute_tool,
    correct_tool_call_descriptions,
    format_pending_confirmation,
    format_tool_result,
    try_rule_based_parse,
)

WRITE_TOOLS = {
    "register_expense",
    "register_income",
    "register_transfer",
    "realize_planned",
    "update_transfer",
    "update_transaction",
    "update_account",
    "update_card",
    "delete_card",
    "delete_transaction",
    "create_account",
    "create_card",
    "create_category",
    "pay_invoice",
}
MAX_RETRIES = 2


def _seed_register_arguments(message: str) -> dict:
    from app.services.tools import extract_description, parse_amount, parse_date

    args: dict = {}
    amount = parse_amount(message.lower())
    if amount:
        args["amount"] = amount
        args["description"] = extract_description(message, amount)
        tx_date = parse_date(message.lower())
        if tx_date:
            args["transaction_date"] = tx_date.isoformat()
    return args


async def _resolve_intent(
    message: str,
    *,
    context: str | None = None,
) -> tuple[ToolCall | None, str]:
    from app.services.intents import wants_register_expense, wants_register_income, wants_realize_planned, wants_pay_invoice

    if wants_realize_planned(message):
        return ToolCall(tool="realize_planned", arguments={}), "rule"
    if wants_pay_invoice(message):
        from app.services.intents import detect_pay_invoice
        return ToolCall(tool="pay_invoice", arguments=detect_pay_invoice(message) or {}), "rule"
    if wants_register_expense(message):
        return ToolCall(tool="register_expense", arguments=_seed_register_arguments(message)), "rule"
    if wants_register_income(message):
        return ToolCall(tool="register_income", arguments=_seed_register_arguments(message)), "rule"

    source = "groq"
    for attempt in range(MAX_RETRIES + 1):
        try:
            tool_call, source = await call_intent_llm(message, context=context)
            if tool_call:
                ToolCall.model_validate(tool_call.model_dump())
                return tool_call, source
        except (ValidationError, ValueError):
            tool_call = None
            if attempt == MAX_RETRIES:
                break

    tool_call = try_rule_based_parse(message)
    if tool_call:
        return tool_call, "rule"

    return None, source


async def process_message(
    db,
    user_id: int,
    message: str,
    *,
    session: dict | None = None,
    confirmed: bool = False,
) -> AgentResponse:
    session = session if session is not None else {}

    if get_pending_movements(session):
        result = try_process_multi_movement_flow(session, message, db, user_id)
        if result:
            return result

    if get_pay_invoice_wizard(session):
        slot = try_process_pay_invoice_wizard(session, message, db=db, user_id=user_id)
        if slot:
            if slot.question and not slot.tool_call:
                return AgentResponse(
                    message=slot.question,
                    suggestions=slot.suggestions,
                    source="wizard",
                )
            if slot.tool_call:
                tool_call = slot.tool_call
                return AgentResponse(
                    message=format_pending_confirmation(tool_call),
                    needs_confirmation=True,
                    pending_action=tool_call.model_dump(),
                    tool_used=tool_call.tool,
                    source="wizard",
                )

    if get_transfer_wizard(session):
        slot = try_process_transfer_wizard(session, message, db=db, user_id=user_id)
        if slot:
            if slot.question and not slot.tool_call:
                return AgentResponse(
                    message=slot.question,
                    suggestions=slot.suggestions,
                    source="wizard",
                )
            if slot.tool_call:
                tool_call = slot.tool_call
                return AgentResponse(
                    message=format_pending_confirmation(tool_call),
                    needs_confirmation=True,
                    pending_action=tool_call.model_dump(),
                    tool_used=tool_call.tool,
                    source="wizard",
                )

    if get_realize_planned_wizard(session):
        slot = try_process_realize_planned_wizard(
            session, message, db=db, user_id=user_id
        )
        if slot:
            if slot.question and not slot.tool_call:
                return AgentResponse(
                    message=slot.question,
                    suggestions=slot.suggestions,
                    source="wizard",
                )
            if slot.tool_call:
                tool_call = slot.tool_call
                return AgentResponse(
                    message=format_pending_confirmation(tool_call),
                    needs_confirmation=True,
                    pending_action=tool_call.model_dump(),
                    tool_used=tool_call.tool,
                    source="wizard",
                )

    if get_transaction_wizard(session):
        result = try_process_transaction_wizard(session, message, db=db, user_id=user_id)
        if result:
            return result
        multi_result = try_begin_from_message(db, user_id, session, message)
        if multi_result:
            return multi_result

    multi_result = try_begin_from_message(db, user_id, session, message)
    if multi_result:
        return multi_result

    if get_card_wizard(session):
        result = try_process_card_wizard(session, message, db=db, user_id=user_id)
        if result:
            return result

    if get_wizard(session):
        result = try_process_account_wizard(session, message)
        if result:
            return result

    if get_category_wizard(session):
        result = try_process_category_wizard(session, message)
        if result:
            return result

    pending_delete_result = try_process_pending_delete(session, message, db, user_id)
    if pending_delete_result:
        return pending_delete_result

    intent_context = build_intent_context(db, user_id, session)
    tool_call, source = await _resolve_intent(message, context=intent_context)

    if not tool_call:
        return AgentResponse(
            message=(
                "Não consegui entender o pedido. "
                + DEFAULT_UNSUPPORTED_MESSAGE
            ),
            source=source,
        )

    if tool_call.tool == "unsupported_action":
        return AgentResponse(
            message=tool_call.arguments.get("reason", DEFAULT_UNSUPPORTED_MESSAGE),
            tool_used="unsupported_action",
            source=source,
        )

    if tool_call.tool == "create_account":
        clear_transaction_wizard(session)
        return begin_account_wizard(session, message, initial=tool_call.arguments)

    if tool_call.tool == "create_card":
        clear_transaction_wizard(session)
        return begin_card_wizard(
            session, message, initial=tool_call.arguments, db=db, user_id=user_id
        )

    if tool_call.tool == "create_category":
        if not get_paused_wizard(session):
            clear_transaction_wizard(session)
        return begin_category_wizard(session, message, initial=tool_call.arguments)

    if tool_call.tool in WRITE_TOOLS and not confirmed:
        if tool_call.tool in {"register_expense", "register_income"}:
            from app.services.transaction_slots import ensure_transaction_slots

            slot_result = ensure_transaction_slots(
                db, user_id, session, tool_call, message
            )
            if slot_result.question:
                return AgentResponse(
                    message=slot_result.question,
                    suggestions=slot_result.suggestions,
                    source=source,
                )
            tool_call = slot_result.tool_call
        if tool_call.tool == "register_transfer":
            from app.services.transfer_slots import ensure_transfer_slots

            slot_result = ensure_transfer_slots(
                db, user_id, session, tool_call, message
            )
            if slot_result.question:
                return AgentResponse(
                    message=slot_result.question,
                    suggestions=slot_result.suggestions,
                    source=source,
                )
            tool_call = slot_result.tool_call
        if tool_call.tool == "realize_planned":
            from app.services.realize_planned_slots import ensure_realize_planned_slots

            slot_result = ensure_realize_planned_slots(
                db, user_id, session, tool_call, message
            )
            if slot_result.question:
                return AgentResponse(
                    message=slot_result.question,
                    suggestions=slot_result.suggestions,
                    source=source,
                )
            tool_call = slot_result.tool_call
        if tool_call.tool == "pay_invoice":
            from app.services.pay_invoice_slots import ensure_pay_invoice_slots

            slot_result = ensure_pay_invoice_slots(
                db, user_id, session, tool_call, message
            )
            if slot_result.question:
                return AgentResponse(
                    message=slot_result.question,
                    suggestions=slot_result.suggestions,
                    source=source,
                )
            tool_call = slot_result.tool_call
        tool_call = correct_tool_call_descriptions(tool_call)
        if tool_call.tool == "delete_transaction":
            resolved, question = prepare_delete_transaction(
                db, user_id, tool_call, session
            )
            if question:
                return AgentResponse(message=question, source=source)
            tool_call = resolved
        clear_agent_flow_state(session)
        return AgentResponse(
            message=format_pending_confirmation(tool_call),
            needs_confirmation=True,
            pending_action=tool_call.model_dump(),
            tool_used=tool_call.tool,
            source=source,
        )

    try:
        outcome = execute_tool(db, user_id, tool_call)
        if tool_call.tool == "create_account":
            clear_wizard(session)
        if tool_call.tool == "create_card":
            clear_card_wizard(session)
        if tool_call.tool == "create_category":
            clear_category_wizard(session)
            created_name = None
            if isinstance(outcome.get("result"), dict):
                created_name = outcome["result"].get("name")
            if created_name:
                resumed = resume_paused_transaction_after_category(
                    session, category_name=created_name
                )
                if resumed:
                    return resumed
        if tool_call.tool in {"register_expense", "register_income", "register_transfer", "realize_planned", "update_transfer", "update_transaction", "update_account", "update_card", "delete_card", "delete_transaction", "pay_invoice"}:
            clear_transaction_wizard(session)
            clear_transfer_wizard(session)
            clear_realize_planned_wizard(session)
            clear_pay_invoice_wizard(session)
        if tool_call.tool == "delete_transaction":
            clear_pending_delete(session)
        return AgentResponse(
            message=format_tool_result(outcome["action"], outcome["result"]),
            tool_used=tool_call.tool,
            data=outcome,
            clear_wizard=tool_call.tool
            in {"create_account", "create_card", "create_category"},
            source=source,
        )
    except (ValidationError, ValueError) as exc:
        return AgentResponse(
            message=(
                f"Não foi possível concluir a ação: {exc}\n"
                + DEFAULT_UNSUPPORTED_MESSAGE
            ),
            source=source,
        )
