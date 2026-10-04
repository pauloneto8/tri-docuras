"""Ferramentas de leitura do agente v2 (funções finas sobre finance.py).

Nenhum cálculo financeiro novo: tudo reutiliza finance.py / credit_cards.py /
recurrence.py / installments.py. O LLM nunca calcula saldo.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    CardInvoice,
    CreditCard,
    InstallmentPlan,
    RecurringRule,
    Transaction,
)
from app.schemas import BudgetStatusInput, SummaryInput, format_brl
from app.services import finance
from app.services.fuzzy_match import fuzzy_find_one
from app.timezone import local_today


def _tx_summary(tx: Transaction) -> dict:
    from app.services.finance import format_transaction

    item = format_transaction(tx)
    item["id"] = tx.id
    item["type"] = tx.type
    item["status"] = tx.status
    return item


def search_transactions(
    db: Session,
    user_id: int,
    *,
    text: str | None = None,
    amount: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    account: str | None = None,
    card: str | None = None,
    category: str | None = None,
    status: str | None = None,
    limit: int = 10,
) -> dict:
    """Busca lançamentos devolvendo ids + resumo. Tolerancia a erro de digitação."""
    stmt = (
        select(Transaction)
        .options(
            joinedload(Transaction.account),
            joinedload(Transaction.category),
            joinedload(Transaction.card),
            joinedload(Transaction.invoice),
        )
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
        .limit(max(1, min(limit, 50)))
    )
    if status in {"planned", "actual"}:
        stmt = stmt.where(Transaction.status == status)
    if date_from:
        try:
            stmt = stmt.where(Transaction.transaction_date >= date.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            stmt = stmt.where(Transaction.transaction_date <= date.fromisoformat(date_to))
        except ValueError:
            pass
    if amount and str(amount).strip():
        try:
            stmt = stmt.where(Transaction.amount_cents == finance.decimal_to_cents(amount))
        except Exception:
            pass
    if account and account.strip():
        try:
            acc = finance.resolve_account_for_transaction(db, user_id, account.strip())
            stmt = stmt.where(Transaction.account_id == acc.id)
        except Exception:
            pass
    if card and card.strip():
        try:
            c = finance.resolve_card_for_transaction(db, user_id, card.strip())
            stmt = stmt.where(Transaction.card_id == c.id)
        except Exception:
            pass
    if category and category.strip():
        cats = finance.list_user_categories(db, user_id)
        match = fuzzy_find_one(category, [c["name"] for c in cats])
        if match:
            cid = next(c["id"] for c in cats if c["name"] == match)
            stmt = stmt.where(Transaction.category_id == cid)

    rows = list(db.scalars(stmt).unique().all())

    # Filtro textual com tolerância a erro (substring exata primeiro, depois fuzzy).
    if text and text.strip():
        needle = text.strip().lower()
        exact = [tx for tx in rows if needle in (tx.description or "").lower()]
        if exact:
            rows = exact
        else:
            match = fuzzy_find_one(text, [tx.description or "" for tx in rows])
            rows = [tx for tx in rows if (tx.description or "") == match]

    return {"results": [_tx_summary(tx) for tx in rows], "count": len(rows)}


def get_balances(db: Session, user_id: int, *, as_of: str | None = None) -> dict:
    ref = None
    if as_of:
        try:
            ref = date.fromisoformat(as_of)
        except ValueError:
            ref = None
    accounts = finance.account_balances(db, user_id, as_of=ref)
    from app.services.credit_cards import list_credit_cards

    return {"accounts": accounts, "cards": list_credit_cards(db, user_id)}


def get_cashflow_projection(db: Session, user_id: int, *, days: int = 30) -> dict:
    today = local_today()
    horizon = today + timedelta(days=max(1, min(days, 180)))
    rows = db.scalars(
        select(Transaction)
        .options(joinedload(Transaction.account), joinedload(Transaction.category))
        .where(
            Transaction.user_id == user_id,
            Transaction.status == "planned",
            Transaction.source_planned_id.is_(None),
            Transaction.transaction_date >= today,
            Transaction.transaction_date <= horizon,
        )
        .order_by(Transaction.transaction_date.asc())
    ).unique().all()
    planned_income = sum(t.amount_cents for t in rows if t.type == "income")
    planned_expense = sum(t.amount_cents for t in rows if t.type == "expense")
    from app.services.credit_cards import list_invoices, invoice_totals

    invoices = []
    for inv in db.scalars(
        select(CardInvoice).where(
            CardInvoice.user_id == user_id,
            CardInvoice.due_date >= today,
            CardInvoice.due_date <= horizon,
            CardInvoice.status != "paid",
            CardInvoice.paid_at.is_(None),
        ).order_by(CardInvoice.due_date.asc())
    ).unique().all():
        invoices.append(
            {
                "id": inv.id,
                "due_date": inv.due_date.isoformat() if inv.due_date else None,
                "card_name": inv.card.name if inv.card else None,
                "total": format_brl(invoice_totals(db, inv)),
            }
        )
    return {
        "from": today.isoformat(),
        "to": horizon.isoformat(),
        "planned_income": format_brl(planned_income),
        "planned_expense": format_brl(planned_expense),
        "planned_result": format_brl(planned_income - planned_expense),
        "pending_planned": [_tx_summary(t) for t in rows],
        "upcoming_invoices": invoices,
    }


def compare_periods(
    db: Session,
    user_id: int,
    *,
    year_a: int,
    month_a: int,
    year_b: int,
    month_b: int,
) -> dict:
    a = finance.get_summary(db, user_id, SummaryInput(year=year_a, month=month_a, period="month"))
    b = finance.get_summary(db, user_id, SummaryInput(year=year_b, month=month_b, period="month"))
    return {
        "period_a": {
            "label": a["period_label"],
            "income": a["income"],
            "expense": a["expense"],
            "result": a["balance"],
        },
        "period_b": {
            "label": b["period_label"],
            "income": b["income"],
            "expense": b["expense"],
            "result": b["balance"],
        },
        "delta_expense": format_brl(b["expense_cents"] - a["expense_cents"]),
        "delta_income": format_brl(b["income_cents"] - a["income_cents"]),
        "delta_result": format_brl(b["balance_cents"] - a["balance_cents"]),
    }


def spending_breakdown(
    db: Session,
    user_id: int,
    *,
    year: int | None = None,
    month: int | None = None,
    group_by: str = "category",
    kind: str = "expense",
) -> dict:
    summary = finance.get_summary(
        db, user_id, SummaryInput(year=year, month=month, period="month")
    )
    if group_by == "category":
        key = "expenses_by_category" if kind == "expense" else "income_by_category"
        return {"period_label": summary["period_label"], "items": summary[key]}
    if group_by in {"account", "card", "description"}:
        start = date.fromisoformat(summary["period_start"])
        end = date.fromisoformat(summary["period_end"])
        tx_type = "expense" if kind == "expense" else "income"
        rows = db.scalars(
            select(Transaction)
            .options(joinedload(Transaction.account), joinedload(Transaction.card))
            .where(
                Transaction.user_id == user_id,
                Transaction.type == tx_type,
                Transaction.transaction_date >= start,
                Transaction.transaction_date <= end,
            )
        ).unique().all()
        buckets: dict[str, int] = {}
        for tx in rows:
            if group_by == "account":
                label = tx.account.name if tx.account else "Sem conta"
            elif group_by == "card":
                label = tx.card.name if tx.card else "Sem cartão"
            else:
                label = (tx.description or "").strip() or "Sem descrição"
            buckets[label] = buckets.get(label, 0) + tx.amount_cents
        items = [
            {"name": name, "amount_cents": value, "amount": format_brl(value)}
            for name, value in sorted(buckets.items(), key=lambda kv: kv[1], reverse=True)
        ]
        return {"period_label": summary["period_label"], "items": items}
    return {"period_label": summary["period_label"], "items": []}


def list_upcoming_bills(db: Session, user_id: int, *, days: int = 7) -> dict:
    today = local_today()
    horizon = today + timedelta(days=max(1, min(days, 90)))
    planned = db.scalars(
        select(Transaction)
        .options(joinedload(Transaction.account), joinedload(Transaction.category))
        .where(
            Transaction.user_id == user_id,
            Transaction.status == "planned",
            Transaction.type == "expense",
            Transaction.transaction_date >= today,
            Transaction.transaction_date <= horizon,
        )
        .order_by(Transaction.transaction_date.asc())
    ).unique().all()
    from app.services.credit_cards import invoice_totals

    invoices = []
    for inv in db.scalars(
        select(CardInvoice)
        .where(
            CardInvoice.user_id == user_id,
            CardInvoice.due_date >= today,
            CardInvoice.due_date <= horizon,
            CardInvoice.status != "paid",
            CardInvoice.paid_at.is_(None),
        )
        .order_by(CardInvoice.due_date.asc())
    ).unique().all():
        invoices.append(
            {
                "invoice_id": inv.id,
                "card_name": inv.card.name if inv.card else None,
                "due_date": inv.due_date.isoformat() if inv.due_date else None,
                "total": format_brl(invoice_totals(db, inv)),
            }
        )
    return {
        "from": today.isoformat(),
        "to": horizon.isoformat(),
        "planned_expenses": [_tx_summary(t) for t in planned],
        "card_invoices": invoices,
    }


def list_recurring_and_installments(db: Session, user_id: int) -> dict:
    rules = db.scalars(
        select(RecurringRule).where(
            RecurringRule.user_id == user_id,
            RecurringRule.is_active.is_(True),
        )
    ).all()
    plans = db.scalars(
        select(InstallmentPlan).where(InstallmentPlan.user_id == user_id)
    ).all()
    return {
        "recurring": [
            {
                "rule_id": r.id,
                "description": getattr(r, "description", None),
                "frequency": getattr(r, "frequency", None),
                "type": getattr(r, "type", None),
            }
            for r in rules
        ],
        "installments": [
            {
                "plan_id": p.id,
                "description": getattr(p, "description", None),
                "count": getattr(p, "count", getattr(p, "installment_count", None)),
            }
            for p in plans
        ],
    }


def get_invoice_detail(
    db: Session,
    user_id: int,
    *,
    card: str | None = None,
    month: int | None = None,
    year: int | None = None,
) -> dict:
    from app.services.credit_cards import list_invoices, list_invoice_movements

    invoices = list_invoices(db, user_id, card_name=card, limit=12)
    if month:
        filtered = []
        for inv in invoices:
            due = inv.get("due_date")
            if not due:
                continue
            try:
                d = date.fromisoformat(due)
            except ValueError:
                continue
            if d.month == month and (year is None or d.year == year):
                filtered.append(inv)
        invoices = filtered
    if not invoices:
        return {"invoice": None, "movements": []}
    chosen = invoices[0]
    movements = list_invoice_movements(db, user_id, chosen["id"])
    return {"invoice": chosen, "movements": movements}


def get_budget_overview(
    db: Session, user_id: int, *, year: int | None = None, month: int | None = None
) -> dict:
    return finance.get_budget_status(db, user_id, BudgetStatusInput(year=year, month=month))
