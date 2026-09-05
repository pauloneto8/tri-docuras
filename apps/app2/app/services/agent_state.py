"""Estado volátil do assistente na sessão HTTP."""

from __future__ import annotations

CANCEL_WORDS = {"cancelar", "desistir", "abortar", "sair", "não", "nao"}


def _session_accepts_nao_answer(session: dict) -> bool:
    """Slots em que 'não' é resposta válida, não cancelamento global."""
    from app.services.realize_planned_slots import (
        _next_field as realize_next_field,
        get_wizard as get_realize_wizard,
    )
    from app.services.transaction_slots import INSTALLMENT_SLOTS, MODE_SLOTS, RECURRENCE_SLOTS
    from app.services.transaction_wizard import _next_field, get_wizard

    wizard = get_wizard(session)
    if wizard:
        field = _next_field(wizard)
        if field in RECURRENCE_SLOTS | MODE_SLOTS | INSTALLMENT_SLOTS:
            return True

    realize = get_realize_wizard(session)
    if realize and realize_next_field(realize) == "same_account":
        return True

    return False


def is_cancel_message(message: str, session: dict | None = None) -> bool:
    lower = message.strip().lower()
    if lower not in CANCEL_WORDS:
        return False
    if lower in {"não", "nao"} and session and _session_accepts_nao_answer(session):
        return False
    return True


def clear_agent_flow_state(session: dict) -> None:
    from app.services.account_wizard import clear_wizard as clear_account_wizard
    from app.services.category_wizard import clear_wizard as clear_category_wizard
    from app.services.delete_flow import clear_pending_delete
    from app.services.multi_movements import clear_pending_movements
    from app.services.realize_planned_slots import clear_wizard as clear_realize_planned_wizard
    from app.services.transfer_slots import clear_wizard as clear_transfer_wizard
    from app.services.transaction_wizard import clear_wizard as clear_transaction_wizard

    from app.services.card_wizard import clear_wizard as clear_card_wizard

    clear_account_wizard(session)
    clear_card_wizard(session)
    clear_category_wizard(session)
    clear_transaction_wizard(session)
    clear_transfer_wizard(session)
    clear_realize_planned_wizard(session)
    clear_pending_movements(session)
    clear_pending_delete(session)
    from app.services.transaction_wizard import clear_paused_wizard

    clear_paused_wizard(session)
