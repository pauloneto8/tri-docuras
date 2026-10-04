"""Resumo proativo diário (Fase 6). Todos os números vêm de Python.

O texto é montado deterministicamente a partir de `finance.py`/`agent_reads.py`;
o LLM (quando ligado) só poderia reescrever — nunca calcula. Assim o resumo é
seguro mesmo sem chave configurada.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Transaction
from app.schemas import BudgetStatusInput, format_brl
from app.timezone import local_today

BUDGET_ALERT_PERCENT = 80.0


def build_daily_digest(db: Session, user_id: int, *, days: int = 3) -> str | None:
    from app.services import finance
    from app.services.agent_reads import list_upcoming_bills

    today = local_today()
    lines: list[str] = []

    overdue = db.scalars(
        select(Transaction)
        .where(
            Transaction.user_id == user_id,
            Transaction.status == "planned",
            Transaction.type == "expense",
            Transaction.transaction_date < today,
        )
        .order_by(Transaction.transaction_date.asc())
        .limit(5)
    ).all()
    for tx in overdue:
        lines.append(
            f"⚠️ Previsto atrasado: {tx.description} — {format_brl(tx.amount_cents)} "
            f"(venceu {tx.transaction_date.strftime('%d/%m')})"
        )

    upcoming = list_upcoming_bills(db, user_id, days=days)
    for tx in upcoming["planned_expenses"][:5]:
        due = tx.get("transaction_date") or tx.get("due_date") or ""
        lines.append(
            f"📅 A pagar: {tx.get('description')} — {tx.get('amount')} ({due})"
        )
    for inv in upcoming["card_invoices"]:
        lines.append(
            f"💳 Fatura {inv.get('card_name')}: {inv.get('total')} vence {inv.get('due_date')}"
        )

    budgets = finance.get_budget_status(db, user_id, BudgetStatusInput())
    for item in budgets:
        if item.get("percent_used", 0) >= BUDGET_ALERT_PERCENT:
            lines.append(
                f"📊 Orçamento {item['category']}: {item['percent_used']:.0f}% usado "
                f"({item['spent']} de {item['limit']})"
            )

    if not lines:
        return None
    return "Bom dia! Seu resumo do AssistFin:\n" + "\n".join(lines)
