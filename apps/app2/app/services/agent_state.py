"""Estado volátil do assistente na sessão HTTP."""

from __future__ import annotations

CANCEL_WORDS = {"cancelar", "desistir", "abortar", "sair", "não", "nao"}


def is_cancel_message(message: str) -> bool:
    return message.strip().lower() in CANCEL_WORDS


def clear_agent_flow_state(session: dict) -> None:
    from app.services.account_wizard import clear_wizard as clear_account_wizard
    from app.services.category_wizard import clear_wizard as clear_category_wizard
    from app.services.delete_flow import clear_pending_delete
    from app.services.multi_movements import clear_pending_movements
    from app.services.realize_planned_slots import clear_wizard as clear_realize_planned_wizard
    from app.services.transfer_slots import clear_wizard as clear_transfer_wizard
    from app.services.transaction_wizard import clear_wizard as clear_transaction_wizard

    clear_account_wizard(session)
    clear_category_wizard(session)
    clear_transaction_wizard(session)
    clear_transfer_wizard(session)
    clear_realize_planned_wizard(session)
    clear_pending_movements(session)
    clear_pending_delete(session)
