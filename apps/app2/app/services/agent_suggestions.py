"""Sugestões (chips) clicáveis para respostas do assistente."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

MAX_CHIPS = 8
CANCEL_CHIP = "Cancelar"


def _with_cancel(options: list[str]) -> list[str]:
    cleaned = [option for option in options if option and option != CANCEL_CHIP]
    if CANCEL_CHIP not in cleaned:
        cleaned.append(CANCEL_CHIP)
    return cleaned


def for_transaction_wizard_field(
    field: str,
    db: Session | None,
    user_id: int | None,
    wizard: dict,
) -> list[str]:
    from app.services.transaction_slots import (
        list_active_account_names,
        list_active_card_names,
        list_category_names,
    )

    if field == "tx_type":
        return _with_cancel(["Despesa", "Receita"])
    if field == "status":
        return _with_cancel(["Realizado", "Previsto"])
    if field == "payment_date":
        return _with_cancel(["Hoje", "Ontem"])
    if field == "competence_date":
        return _with_cancel(["Hoje"])
    if field == "due_date":
        return _with_cancel(["Hoje", "Amanhã"])
    if field == "payment_mode":
        return _with_cancel(["Único", "Fixo", "Parcelado"])
    if field == "payment_source":
        return _with_cancel(["Cartão de crédito", "Conta bancária"])
    if field == "is_recurring":
        return _with_cancel(["Sim", "Não"])
    if field == "frequency":
        return _with_cancel(["Diária", "Semanal", "Mensal"])
    if field == "recurrence_end_date":
        return _with_cancel(["Não", "Hoje"])
    if field == "installment_count":
        return _with_cancel(["2", "3", "6", "12"])
    if field == "installment_interval":
        return _with_cancel(["Mensal", "Semanal", "Quinzenal"])
    if field == "installment_start_index":
        count = int(wizard.get("installment_count") or 12)
        options = ["1 (primeira)"]
        options.extend(str(i) for i in range(2, min(count, 6) + 1))
        return _with_cancel(options)
    if field == "installment_amount_basis":
        return _with_cancel(["Valor total", "Valor da parcela"])
    if field == "account_name" and db is not None and user_id is not None:
        names = list_active_account_names(db, user_id)[:MAX_CHIPS]
        return _with_cancel(names) if names else _with_cancel([])
    if field == "card_name" and db is not None and user_id is not None:
        names = list_active_card_names(db, user_id)[:MAX_CHIPS]
        return _with_cancel(names) if names else _with_cancel([])
    if field == "category_name" and db is not None and user_id is not None:
        tx_type = wizard.get("tx_type") or "expense"
        names = list_category_names(db, user_id, tx_type)
        chips: list[str] = []
        suggestion = wizard.get("suggested_category")
        if suggestion:
            chips.append("Sim")
        chips.extend(name for name in names if name != suggestion)
        reserved = ["Nova categoria"]
        limit = max(1, MAX_CHIPS - len(reserved))
        return _with_cancel(chips[:limit] + reserved)
    return _with_cancel([])


def for_card_wizard_field(field: str, db=None, user_id: int | None = None) -> list[str]:
    if field == "closing_day":
        return _with_cancel(["5", "10", "15", "20", "25"])
    if field == "due_day":
        return _with_cancel(["10", "15", "17", "20", "25"])
    if field == "credit_limit":
        return _with_cancel(["Pular"])
    if field == "institution":
        return _with_cancel(["Pular"])
    if field == "settlement_account_name" and db is not None and user_id is not None:
        from app.services.transaction_slots import list_active_account_names

        names = list_active_account_names(db, user_id)[:MAX_CHIPS]
        return _with_cancel(names) if names else _with_cancel([])
    return _with_cancel([])


def for_account_wizard_field(field: str) -> list[str]:
    if field == "account_type":
        return _with_cancel(["Corrente", "Poupança", "Carteira", "Cartão"])
    if field == "institution":
        return _with_cancel(["Pular"])
    if field == "closing_day":
        return _with_cancel(["5", "10", "15", "20", "25"])
    if field == "due_day":
        return _with_cancel(["10", "15", "17", "20", "25"])
    if field == "credit_limit":
        return _with_cancel(["Pular"])
    if field == "opening_balance":
        return _with_cancel(["0", "Pular"])
    if field == "opening_balance_date":
        return _with_cancel(["Hoje", "Ontem"])
    return _with_cancel([])


def for_pay_invoice_field(
    field: str,
    db: Session,
    user_id: int,
    wizard: dict,
) -> list[str]:
    from app.services.pay_invoice_slots import _list_card_names, _list_debit_names

    if field == "account_name":
        return _with_cancel(_list_card_names(db, user_id)[:MAX_CHIPS])
    if field == "from_account_name":
        return _with_cancel(_list_debit_names(db, user_id)[:MAX_CHIPS])
    if field == "payment_date":
        return _with_cancel(["Hoje", "Ontem"])
    return _with_cancel([])


def for_category_wizard_field(field: str) -> list[str]:
    if field == "category_type":
        return _with_cancel(["Despesa", "Receita"])
    return _with_cancel([])


def for_realize_planned_field(
    field: str,
    db: Session,
    user_id: int,
    wizard: dict,
) -> list[str]:
    from app.services.realize_planned_slots import _pending_planned_labels
    from app.services.transaction_slots import list_active_account_names

    if field == "planned":
        labels = [label for _, label in _pending_planned_labels(db, user_id)]
        return _with_cancel(labels[:MAX_CHIPS]) if labels else _with_cancel([])
    if field == "payment_date":
        return _with_cancel(["Hoje", "Ontem"])
    if field == "same_account":
        return _with_cancel(["Sim", "Outra conta"])
    if field == "account_name":
        planned = wizard.get("planned_account_name")
        names = [
            n for n in list_active_account_names(db, user_id) if n != planned
        ][:MAX_CHIPS]
        return _with_cancel(names) if names else _with_cancel([])
    return _with_cancel([])


def for_transfer_wizard_field(
    field: str,
    db: Session,
    user_id: int,
    wizard: dict,
) -> list[str]:
    from app.services.transaction_slots import list_active_account_names

    names = list_active_account_names(db, user_id)[:MAX_CHIPS]
    if field == "from_account_name":
        return _with_cancel(names) if names else _with_cancel([])
    if field == "to_account_name":
        from_name = wizard.get("from_account_name")
        filtered = [n for n in names if n != from_name]
        return _with_cancel(filtered) if filtered else _with_cancel([])
    return _with_cancel([])


def for_multi_slot(
    slot: str,
    db: Session,
    user_id: int,
    pending: dict,
    item_idx: int,
) -> list[str]:
    from app.services.transaction_slots import (
        list_active_account_names,
        list_category_names,
    )

    if slot == "account_name":
        names = list_active_account_names(db, user_id)[:MAX_CHIPS]
        return _with_cancel(names) if names else _with_cancel([])
    if slot == "category_name" and item_idx >= 0:
        item = pending["items"][item_idx]
        tx_type = item.get("tx_type", "expense")
        names = list_category_names(db, user_id, tx_type)[:MAX_CHIPS]
        return _with_cancel(names) if names else _with_cancel([])
    return _with_cancel([])
