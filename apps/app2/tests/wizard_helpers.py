"""Helpers para testes do wizard de transação."""

from app.services.transaction_wizard import get_wizard, try_process_transaction_wizard


def decline_recurring(session: dict, *, db=None, user_id=None) -> None:
    """Responde 'Não' aos slots de recorrência quando ativos."""
    from app.services.transaction_wizard import _next_field

    wizard = get_wizard(session)
    if not wizard:
        return
    field = _next_field(wizard)
    if field == "is_recurring":
        try_process_transaction_wizard(
            session, "Não", db=db, user_id=user_id
        )


def decline_recurring_slot(session: dict, db, user_id: int):
    """Versão para process_slot_answer flows."""
    from app.services.transaction_slots import process_slot_answer

    wizard = get_wizard(session)
    if not wizard:
        return None
    from app.services.transaction_wizard import _next_field

    if _next_field(wizard) == "is_recurring":
        return process_slot_answer(db, user_id, session, "Não")
    return None
