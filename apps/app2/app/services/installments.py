"""Motor de lançamentos parcelados (funções puras + cancelamento)."""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
from typing import Literal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import InstallmentPlan, Transaction, CreditCard

InstallmentInterval = Literal["monthly", "weekly", "biweekly"]

INTERVAL_LABELS = {
    "monthly": "mensal",
    "weekly": "semanal",
    "biweekly": "quinzenal",
}


def parse_installment_interval(value: str | None) -> InstallmentInterval | None:
    if not value:
        return None
    normalized = value.strip().lower()
    mapping = {
        "monthly": "monthly",
        "mensal": "monthly",
        "mes": "monthly",
        "mês": "monthly",
        "weekly": "weekly",
        "semanal": "weekly",
        "semana": "weekly",
        "biweekly": "biweekly",
        "quinzenal": "biweekly",
        "quinzena": "biweekly",
    }
    return mapping.get(normalized)  # type: ignore[return-value]


def parse_installment_count(message: str) -> int | None:
    text = message.strip().lower()
    if not text:
        return None
    match = re.search(r"(\d+)\s*x\b", text)
    if match:
        n = int(match.group(1))
        return n if n >= 2 else None
    match = re.search(r"(\d+)\s*(?:vezes|parcelas?)", text)
    if match:
        n = int(match.group(1))
        return n if n >= 2 else None
    if text.isdigit():
        n = int(text)
        return n if n >= 2 else None
    return None


def parse_installment_start_index(message: str, max_count: int) -> int | None:
    text = message.strip().lower()
    if not text or max_count < 1:
        return None
    if text in {"1", "primeira", "primeiro", "sim", "s", "1 (primeira)"}:
        return 1
    match = re.search(r"(\d+)\s*(?:ª|a)?\s*(?:parcela)?", text)
    if match:
        n = int(match.group(1))
        return n if 1 <= n <= max_count else None
    if text.isdigit():
        n = int(text)
        return n if 1 <= n <= max_count else None
    ordinals = {
        "segunda": 2,
        "terceira": 3,
        "quarta": 4,
        "quinta": 5,
        "sexta": 6,
        "sétima": 7,
        "setima": 7,
        "oitava": 8,
        "nona": 9,
        "décima": 10,
        "decima": 10,
    }
    for word, n in ordinals.items():
        if word in text and n <= max_count:
            return n
    return None


def split_cents(total_cents: int, count: int) -> list[int]:
    if count < 2:
        raise ValueError("Parcelamento exige pelo menos 2 parcelas.")
    base = total_cents // count
    remainder = total_cents % count
    amounts = [base] * count
    amounts[-1] += remainder
    return amounts


def repeat_cents(unit_cents: int, count: int) -> list[int]:
    if count < 2:
        raise ValueError("Parcelamento exige pelo menos 2 parcelas.")
    return [unit_cents] * count


def _last_day_of_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, _last_day_of_month(year, month))
    return date(year, month, day)


def due_date_for_index(
    start_date: date, index: int, interval: InstallmentInterval
) -> date:
    """index é 1-based (1 = primeira parcela)."""
    if index <= 1:
        return start_date
    steps = index - 1
    if interval == "weekly":
        return start_date + timedelta(days=7 * steps)
    if interval == "biweekly":
        return start_date + timedelta(days=14 * steps)
    return _add_months(start_date, steps)


def format_installment_label(index: int, count: int, interval: str | None) -> str:
    label = INTERVAL_LABELS.get(interval or "", interval or "")
    return f"{index}/{count} · {label}"


def create_installment_plan(
    db: Session,
    user_id: int,
    *,
    account_id: int,
    card_id: int | None = None,
    category_id: int | None,
    tx_type: str,
    total_cents: int,
    installment_count: int,
    interval: InstallmentInterval,
    start_date: date,
    description: str,
    first_status: str = "planned",
    competence_date: date | None = None,
    due_date: date | None = None,
    payment_date: date | None = None,
    transaction_date: date | None = None,
    amount_basis: Literal["total", "installment"] = "total",
    start_index: int = 1,
) -> tuple[InstallmentPlan, list[Transaction]]:
    """Cria plano e N transações parceladas. Importa finance.create_transaction sob demanda."""
    from app.schemas import TransactionCreate
    from app.services.finance import create_transaction

    if installment_count < 2:
        raise ValueError("Parcelamento exige pelo menos 2 parcelas.")
    if start_index < 1 or start_index > installment_count:
        raise ValueError("Parcela inicial inválida para o número de parcelas informado.")

    if amount_basis == "installment":
        all_amounts = repeat_cents(total_cents, installment_count)
        plan_total_cents = total_cents * installment_count
    else:
        all_amounts = split_cents(total_cents, installment_count)
        plan_total_cents = total_cents
    plan = InstallmentPlan(
        user_id=user_id,
        account_id=account_id,
        category_id=category_id,
        type=tx_type,
        total_cents=plan_total_cents,
        installment_count=installment_count,
        interval=interval,
        start_date=start_date,
        description=description,
        is_active=True,
    )
    db.add(plan)
    db.flush()

    card = db.get(CreditCard, card_id) if card_id is not None else None
    transactions: list[Transaction] = []
    base_desc = description.strip()
    for idx in range(start_index, installment_count + 1):
        # schedule_date = data da compra da parcela (âncora do ciclo no cartão).
        schedule_date = due_date_for_index(start_date, idx - start_index + 1, interval)
        if card:
            from app.services.credit_cards import cycle_for_purchase

            _, _, due = cycle_for_purchase(card.closing_day, card.due_day, schedule_date)
        else:
            due = schedule_date
        part_desc = f"{base_desc} {idx}/{installment_count}"
        is_first = idx == start_index
        if card:
            status = "planned"
            tx_payment = None
        else:
            status = first_status if is_first else "planned"
            tx_payment = payment_date if is_first and first_status == "actual" else None
        # Competência da parcela = data da compra no cronograma (1ª pode herdar competence_date).
        tx_comp = competence_date if is_first and competence_date else schedule_date
        tx_cash_date = (payment_date or transaction_date or due) if is_first else None
        tx = create_transaction(
            db,
            user_id,
            TransactionCreate(
                account_id=account_id,
                card_id=card_id,
                category_id=category_id,
                type=tx_type,  # type: ignore[arg-type]
                amount_cents=all_amounts[idx - 1],
                description=part_desc,
                competence_date=tx_comp,
                due_date=due,
                payment_date=tx_payment,
                transaction_date=tx_cash_date,
                status=status,  # type: ignore[arg-type]
                installment_plan_id=plan.id,
                installment_index=idx,
            ),
        )
        transactions.append(tx)

    return plan, transactions


def cancel_installment_plan(db: Session, user_id: int, plan_id: int) -> None:
    plan = db.scalar(
        select(InstallmentPlan).where(
            InstallmentPlan.id == plan_id,
            InstallmentPlan.user_id == user_id,
        )
    )
    if not plan:
        raise ValueError("Plano de parcelas não encontrado.")
    plan.is_active = False
    db.execute(
        delete(Transaction).where(
            Transaction.installment_plan_id == plan_id,
            Transaction.user_id == user_id,
            Transaction.status == "planned",
        )
    )
    db.commit()
