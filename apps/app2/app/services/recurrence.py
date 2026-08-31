"""Motor de geração de lançamentos fixos (recorrência)."""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Literal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from app.models import RecurringRule, Transaction
from app.timezone import local_today

Frequency = Literal["daily", "weekly", "monthly"]

HORIZON_MONTHS = 3

FREQUENCY_LABELS = {
    "daily": "diária",
    "weekly": "semanal",
    "monthly": "mensal",
}


def parse_frequency(value: str | None) -> Frequency | None:
    if not value:
        return None
    normalized = value.strip().lower()
    mapping = {
        "daily": "daily",
        "diaria": "daily",
        "diário": "daily",
        "diária": "daily",
        "dia": "daily",
        "weekly": "weekly",
        "semanal": "weekly",
        "semana": "weekly",
        "monthly": "monthly",
        "mensal": "monthly",
        "mes": "monthly",
        "mês": "monthly",
    }
    return mapping.get(normalized)  # type: ignore[return-value]


def anchor_from_date(d: date) -> tuple[int | None, int | None]:
    return d.day, d.weekday()


def horizon_end(today: date, end_date: date | None) -> date:
    rolling = _add_months(today, HORIZON_MONTHS)
    if end_date is not None and end_date < rolling:
        return end_date
    return rolling


def _last_day_of_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, _last_day_of_month(year, month))
    return date(year, month, day)


def _monthly_on_anchor(year: int, month: int, anchor_day: int) -> date:
    day = min(anchor_day, _last_day_of_month(year, month))
    return date(year, month, day)


def next_occurrence(rule: RecurringRule, from_date: date) -> date:
    if rule.frequency == "daily":
        return from_date + timedelta(days=1)
    if rule.frequency == "weekly":
        anchor = rule.anchor_weekday if rule.anchor_weekday is not None else from_date.weekday()
        days_ahead = (anchor - from_date.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        return from_date + timedelta(days=days_ahead)
    anchor_day = rule.anchor_day if rule.anchor_day is not None else from_date.day
    year, month = from_date.year, from_date.month
    if month == 12:
        year += 1
        month = 1
    else:
        month += 1
    return _monthly_on_anchor(year, month, anchor_day)


def iter_occurrences(
    rule: RecurringRule,
    *,
    start: date,
    end: date,
) -> list[date]:
    if start > end:
        return []
    effective_start = max(start, rule.start_date)
    if rule.end_date is not None and effective_start > rule.end_date:
        return []

    dates: list[date] = []
    current = effective_start
    if rule.frequency == "monthly" and rule.anchor_day is not None:
        current = _monthly_on_anchor(current.year, current.month, rule.anchor_day)
        if current < effective_start:
            current = next_occurrence(rule, current)

    while current <= end:
        if rule.end_date is not None and current > rule.end_date:
            break
        dates.append(current)
        current = next_occurrence(rule, current)
    return dates


def create_recurring_rule(
    db: Session,
    user_id: int,
    *,
    account_id: int,
    category_id: int | None,
    tx_type: str,
    amount_cents: int,
    description: str,
    frequency: Frequency,
    start_date: date,
    end_date: date | None = None,
) -> RecurringRule:
    anchor_day, anchor_weekday = anchor_from_date(start_date)
    rule = RecurringRule(
        user_id=user_id,
        account_id=account_id,
        category_id=category_id,
        type=tx_type,
        amount_cents=amount_cents,
        description=description,
        frequency=frequency,
        start_date=start_date,
        end_date=end_date,
        anchor_day=anchor_day if frequency == "monthly" else None,
        anchor_weekday=anchor_weekday if frequency == "weekly" else None,
        is_active=True,
    )
    db.add(rule)
    db.flush()
    return rule


def _existing_due_dates(db: Session, rule_id: int) -> set[date]:
    rows = db.scalars(
        select(Transaction.due_date).where(Transaction.recurrence_id == rule_id)
    ).all()
    return set(rows)


def ensure_recurring_horizon(
    db: Session,
    user_id: int,
    *,
    rule_id: int | None = None,
    today: date | None = None,
) -> int:
    """Gera previstos faltantes até o horizonte. Retorna quantidade criada."""
    ref = today or local_today()
    stmt = (
        select(RecurringRule)
        .options(joinedload(RecurringRule.account), joinedload(RecurringRule.category))
        .where(RecurringRule.user_id == user_id, RecurringRule.is_active.is_(True))
    )
    if rule_id is not None:
        stmt = stmt.where(RecurringRule.id == rule_id)
    rules = db.scalars(stmt).unique().all()
    created = 0

    for rule in rules:
        end = horizon_end(ref, rule.end_date)
        existing = _existing_due_dates(db, rule.id)
        if existing:
            last_due = max(existing)
            start_from = next_occurrence(rule, last_due)
        else:
            start_from = rule.start_date

        for due in iter_occurrences(rule, start=start_from, end=end):
            if due in existing:
                continue
            tx = Transaction(
                user_id=user_id,
                account_id=rule.account_id,
                category_id=rule.category_id,
                type=rule.type,
                amount_cents=rule.amount_cents,
                description=rule.description,
                competence_date=due,
                due_date=due,
                payment_date=None,
                transaction_date=due,
                status="planned",
                recurrence_id=rule.id,
            )
            db.add(tx)
            existing.add(due)
            created += 1

    if created:
        db.commit()
    return created


def deactivate_recurring_rule(db: Session, user_id: int, rule_id: int) -> dict:
    rule = db.scalar(
        select(RecurringRule).where(
            RecurringRule.id == rule_id,
            RecurringRule.user_id == user_id,
        )
    )
    if not rule:
        raise ValueError("Série fixa não encontrada.")

    realized_planned_ids = set(
        db.scalars(
            select(Transaction.source_planned_id).where(
                Transaction.user_id == user_id,
                Transaction.source_planned_id.isnot(None),
            )
        ).all()
    )
    delete_stmt = delete(Transaction).where(
        Transaction.recurrence_id == rule_id,
        Transaction.user_id == user_id,
        Transaction.status == "planned",
    )
    if realized_planned_ids:
        delete_stmt = delete_stmt.where(Transaction.id.not_in(realized_planned_ids))
    db.execute(delete_stmt)
    rule.is_active = False
    db.commit()
    return {
        "id": rule.id,
        "description": rule.description,
        "frequency": rule.frequency,
        "frequency_label": FREQUENCY_LABELS.get(rule.frequency, rule.frequency),
        "is_active": False,
    }


def format_recurrence_label(frequency: str | None) -> str | None:
    if not frequency:
        return None
    label = FREQUENCY_LABELS.get(frequency, frequency)
    return f"Fixo · {label}"
