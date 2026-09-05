"""Motor de cartões de crédito e faturas."""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Account, CardInvoice, CreditCard, Transaction
from app.schemas import RegisterExpenseInput, format_brl
from app.timezone import local_today

InvoiceStatus = Literal["open", "closed", "paid"]

STATUS_LABELS = {
    "open": "Aberta",
    "closed": "Fechada",
    "paid": "Paga",
}

MONTH_NAME_TO_NUM = {
    "janeiro": 1,
    "jan": 1,
    "fevereiro": 2,
    "fev": 2,
    "março": 3,
    "marco": 3,
    "mar": 3,
    "abril": 4,
    "abr": 4,
    "maio": 5,
    "mai": 5,
    "junho": 6,
    "jun": 6,
    "julho": 7,
    "jul": 7,
    "agosto": 8,
    "ago": 8,
    "setembro": 9,
    "set": 9,
    "outubro": 10,
    "out": 10,
    "novembro": 11,
    "nov": 11,
    "dezembro": 12,
    "dez": 12,
}


def _last_day_of_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _anchor_day(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, _last_day_of_month(year, month)))


def _add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    return _anchor_day(year, month, d.day)


def parse_day_of_month(message: str) -> int | None:
    text = message.strip().lower()
    if not text:
        return None
    if text.isdigit():
        day = int(text)
        return day if 1 <= day <= 31 else None
    match = re.search(r"\b(\d{1,2})\b", text)
    if match:
        day = int(match.group(1))
        return day if 1 <= day <= 31 else None
    return None


def cycle_end_for_purchase(purchase_date: date, closing_day: int) -> date:
    if purchase_date.day > closing_day:
        next_month = _add_months(purchase_date.replace(day=1), 1)
        return _anchor_day(next_month.year, next_month.month, closing_day)
    return _anchor_day(purchase_date.year, purchase_date.month, closing_day)


def due_date_for_cycle(cycle_end: date, closing_day: int, due_day: int) -> date:
    if due_day > closing_day:
        return _anchor_day(cycle_end.year, cycle_end.month, due_day)
    next_month = _add_months(cycle_end.replace(day=1), 1)
    return _anchor_day(next_month.year, next_month.month, due_day)


def cycle_start_for_end(cycle_end: date, closing_day: int) -> date:
    prev_month = _add_months(cycle_end.replace(day=1), -1)
    prev_end = _anchor_day(prev_month.year, prev_month.month, closing_day)
    return prev_end + timedelta(days=1)


def cycle_for_purchase(
    closing_day: int, due_day: int, purchase_date: date
) -> tuple[date, date, date]:
    """Retorna (cycle_start, cycle_end, due_date) para uma compra."""
    cycle_end = cycle_end_for_purchase(purchase_date, closing_day)
    cycle_start = cycle_start_for_end(cycle_end, closing_day)
    due = due_date_for_cycle(cycle_end, closing_day, due_day)
    return cycle_start, cycle_end, due


def get_or_create_invoice(
    db: Session,
    card: CreditCard,
    purchase_date: date,
) -> CardInvoice:
    cycle_start, cycle_end, due = cycle_for_purchase(
        card.closing_day, card.due_day, purchase_date
    )

    existing = db.scalar(
        select(CardInvoice).where(
            CardInvoice.card_id == card.id,
            CardInvoice.due_date == due,
        )
    )
    if existing:
        return existing

    invoice = CardInvoice(
        user_id=card.user_id,
        card_id=card.id,
        cycle_start=cycle_start,
        cycle_end=cycle_end,
        due_date=due,
        status="open",
    )
    db.add(invoice)
    db.flush()
    return invoice


def close_due_invoices(db: Session, user_id: int | None = None, today: date | None = None) -> int:
    today = today or local_today()
    stmt = select(CardInvoice).where(
        CardInvoice.status == "open",
        CardInvoice.cycle_end < today,
    )
    if user_id is not None:
        stmt = stmt.where(CardInvoice.user_id == user_id)
    invoices = db.scalars(stmt).all()
    for inv in invoices:
        inv.status = "closed"
    if invoices:
        db.commit()
    return len(invoices)


def ensure_invoices_for_card(
    db: Session, card: CreditCard, today: date | None = None
) -> None:
    today = today or local_today()
    get_or_create_invoice(db, card, today)
    next_cycle = cycle_end_for_purchase(today, card.closing_day)
    if next_cycle <= today:
        next_purchase = today + timedelta(days=1)
    else:
        next_purchase = today
    get_or_create_invoice(db, card, next_purchase)
    db.commit()


def sync_credit_cards(db: Session, user_id: int, today: date | None = None) -> None:
    today = today or local_today()
    close_due_invoices(db, user_id=user_id, today=today)
    cards = db.scalars(
        select(CreditCard).where(
            CreditCard.user_id == user_id,
            CreditCard.is_active.is_(True),
        )
    ).all()
    for card in cards:
        ensure_invoices_for_card(db, card, today=today)


def invoice_totals(db: Session, invoice: CardInvoice) -> int:
    expense = db.scalar(
        select(func.coalesce(func.sum(Transaction.amount_cents), 0)).where(
            Transaction.invoice_id == invoice.id,
            Transaction.type == "expense",
        )
    )
    income = db.scalar(
        select(func.coalesce(func.sum(Transaction.amount_cents), 0)).where(
            Transaction.invoice_id == invoice.id,
            Transaction.type == "income",
        )
    )
    return int(expense or 0) - int(income or 0)


def unpaid_invoice_total(db: Session, card_id: int) -> int:
    invoices = db.scalars(
        select(CardInvoice).where(
            CardInvoice.card_id == card_id,
            CardInvoice.status.in_(("open", "closed")),
        )
    ).all()
    return sum(invoice_totals(db, inv) for inv in invoices)


def settle_invoice_planned_transactions(
    db: Session,
    user_id: int,
    invoice: CardInvoice,
    pay_date: date,
) -> list[Transaction]:
    """Marca previstos da fatura como realizados ao pagar — evita duplicar saída."""
    planned_txs = list(
        db.scalars(
            select(Transaction).where(
                Transaction.user_id == user_id,
                Transaction.invoice_id == invoice.id,
                Transaction.status == "planned",
            )
        ).all()
    )
    settled: list[Transaction] = []
    for tx in planned_txs:
        already = db.scalar(
            select(Transaction.id).where(
                Transaction.user_id == user_id,
                Transaction.source_planned_id == tx.id,
            )
        )
        if already:
            continue
        tx.status = "actual"
        tx.payment_date = pay_date
        tx.transaction_date = pay_date
        settled.append(tx)
    if settled:
        db.flush()
    return settled


def available_limit_cents(db: Session, card: CreditCard) -> int | None:
    if card.credit_limit_cents is None:
        return None
    used = unpaid_invoice_total(db, card.id)
    return max(0, int(card.credit_limit_cents) - used)


def invoice_due_for_purchase(card: CreditCard, purchase_date: date) -> date:
    """Vencimento da fatura do cartão para uma compra na data informada."""
    return cycle_for_purchase(card.closing_day, card.due_day, purchase_date)[2]


def purchase_anchor_for_invoice(tx: Transaction) -> date | None:
    """Data de compra usada no ciclo quando não há vencimento de fatura explícito."""
    for value in (
        tx.payment_date,
        tx.competence_date,
        tx.transaction_date,
    ):
        if value is not None:
            return value
    return tx.due_date


def _invoice_for_explicit_due(
    db: Session, card: CreditCard, due: date
) -> CardInvoice | None:
    """Localiza ou cria fatura com vencimento exatamente igual a `due`."""
    existing = db.scalar(
        select(CardInvoice).where(
            CardInvoice.card_id == card.id,
            CardInvoice.due_date == due,
        )
    )
    if existing:
        return existing

    # Compra no dia de fechamento do mês do vencimento (ou mês anterior se due < closing).
    probe = _anchor_day(due.year, due.month, card.closing_day)
    _, _, computed = cycle_for_purchase(card.closing_day, card.due_day, probe)
    if computed == due:
        return get_or_create_invoice(db, card, probe)
    prev = _add_months(due.replace(day=1), -1)
    probe = _anchor_day(prev.year, prev.month, card.closing_day)
    _, _, computed = cycle_for_purchase(card.closing_day, card.due_day, probe)
    if computed == due:
        return get_or_create_invoice(db, card, probe)
    return None


def assign_transaction_to_invoice(
    db: Session, card: CreditCard, tx: Transaction
) -> CardInvoice | None:
    if tx.type not in ("expense", "income"):
        return None
    # Vencimento explícito identifica a fatura (não serve como data de compra:
    # due_day costuma ser depois do fechamento).
    if tx.due_date is not None:
        invoice = _invoice_for_explicit_due(db, card, tx.due_date)
        if invoice is not None:
            tx.invoice_id = invoice.id
            db.flush()
            return invoice
    purchase_date = purchase_anchor_for_invoice(tx)
    if purchase_date is None:
        return None
    invoice = get_or_create_invoice(db, card, purchase_date)
    tx.invoice_id = invoice.id
    if tx.due_date is None:
        tx.due_date = invoice.due_date
    db.flush()
    return invoice


def resolve_invoice_by_due_period(
    db: Session,
    card: CreditCard,
    *,
    due_month: int,
    due_year: int,
) -> CardInvoice:
    """Localiza ou cria a fatura cujo vencimento cai no mês/ano informados."""
    if not (1 <= due_month <= 12):
        raise ValueError("Mês de vencimento da fatura inválido.")
    if due_year < 2000 or due_year > 2100:
        raise ValueError("Ano de vencimento da fatura inválido.")

    existing = db.scalar(
        select(CardInvoice)
        .where(
            CardInvoice.card_id == card.id,
            CardInvoice.user_id == card.user_id,
            func.extract("month", CardInvoice.due_date) == due_month,
            func.extract("year", CardInvoice.due_date) == due_year,
        )
        .order_by(CardInvoice.due_date.asc())
        .limit(1)
    )
    if existing:
        return existing

    # Âncora no ciclo: compra no último dia do ciclo (fechamento) do mês alvo.
    probe = _anchor_day(due_year, due_month, card.closing_day)
    invoice = get_or_create_invoice(db, card, probe)
    if invoice.due_date.month != due_month or invoice.due_date.year != due_year:
        # Fechamento após o due_day: tentar um dia antes do fechamento do mês.
        probe = _anchor_day(due_year, due_month, max(1, card.closing_day - 1))
        invoice = get_or_create_invoice(db, card, probe)
    if invoice.due_date.month != due_month or invoice.due_date.year != due_year:
        raise ValueError(
            f"Não foi possível localizar fatura com vencimento em {due_month:02d}/{due_year}."
        )
    return invoice


def purchase_date_in_invoice_cycle(invoice: CardInvoice) -> date:
    """Data de compra válida dentro do ciclo da fatura (regra estrita)."""
    return invoice.cycle_end


def reassign_card_transaction_invoice(
    db: Session,
    card: CreditCard,
    tx: Transaction,
    invoice: CardInvoice,
) -> CardInvoice:
    """Move o lançamento para a fatura alvo e alinha datas do ciclo."""
    if invoice.card_id != card.id:
        raise ValueError("Fatura não pertence a este cartão.")
    anchor = purchase_date_in_invoice_cycle(invoice)
    tx.invoice_id = invoice.id
    tx.due_date = invoice.due_date
    if tx.status == "planned":
        tx.transaction_date = invoice.due_date
        tx.payment_date = None
    elif tx.transaction_date is None:
        tx.transaction_date = invoice.due_date
    # Competência: preserva se já estiver no ciclo; senão usa âncora do ciclo.
    if tx.competence_date is None or not (
        invoice.cycle_start <= tx.competence_date <= invoice.cycle_end
    ):
        tx.competence_date = anchor
    db.flush()
    return invoice


def parse_invoice_period_hint(
    message: str, *, ref_date: date | None = None
) -> tuple[int, int] | None:
    """Extrai mês/ano de referência (ex.: 'fatura de setembro')."""
    ref = ref_date or local_today()
    lower = message.lower()
    for name, month in MONTH_NAME_TO_NUM.items():
        if re.search(rf"\b{re.escape(name)}\b", lower):
            year = ref.year
            if month > ref.month + 2:
                year -= 1
            return month, year
    match = re.search(r"\bfatura\b.*\b(\d{1,2})[/\-](\d{4})\b", lower)
    if match:
        month = int(match.group(1))
        year = int(match.group(2))
        if 1 <= month <= 12:
            return month, year
    return None


def resolve_payable_invoice(
    db: Session,
    user_id: int,
    *,
    invoice_id: int | None = None,
    card_name: str | None = None,
    due_month: int | None = None,
    due_year: int | None = None,
) -> tuple[CardInvoice, CreditCard]:
    """Localiza fatura em aberto/fechada para pagamento."""
    from app.services.finance import resolve_card_for_transaction

    if invoice_id is not None:
        invoice = db.scalar(
            select(CardInvoice).where(
                CardInvoice.id == invoice_id,
                CardInvoice.user_id == user_id,
            )
        )
        if not invoice:
            raise ValueError("Fatura não encontrada.")
        card = db.get(CreditCard, invoice.card_id)
        if not card or card.user_id != user_id:
            raise ValueError("Cartão não encontrado.")
        return invoice, card

    card: CreditCard | None = None
    if card_name and card_name.strip():
        card = resolve_card_for_transaction(db, user_id, card_name.strip())
    else:
        cards = db.scalars(
            select(CreditCard).where(
                CreditCard.user_id == user_id,
                CreditCard.is_active.is_(True),
            )
        ).all()
        if len(cards) == 1:
            card = cards[0]
        elif not cards:
            raise ValueError("Nenhum cartão cadastrado.")
        else:
            raise ValueError("Informe o cartão.")

    stmt = (
        select(CardInvoice)
        .where(
            CardInvoice.card_id == card.id,
            CardInvoice.user_id == user_id,
            CardInvoice.status.in_(("open", "closed")),
        )
        .order_by(CardInvoice.due_date.asc())
    )
    if due_month is not None and due_year is not None:
        stmt = stmt.where(
            func.extract("month", CardInvoice.due_date) == due_month,
            func.extract("year", CardInvoice.due_date) == due_year,
        )
    invoice = db.scalar(stmt.limit(1))
    if not invoice:
        if due_month is not None and due_year is not None:
            month_label = f"{due_month:02d}/{due_year}"
            raise ValueError(
                f"Nenhuma fatura em aberto com vencimento em {month_label}."
            )
        raise ValueError("Fatura não encontrada.")
    return invoice, card


def preview_payable_invoice(
    db: Session,
    user_id: int,
    *,
    invoice_id: int | None = None,
    card_name: str | None = None,
    due_month: int | None = None,
    due_year: int | None = None,
) -> dict | None:
    try:
        invoice, card = resolve_payable_invoice(
            db,
            user_id,
            invoice_id=invoice_id,
            card_name=card_name,
            due_month=due_month,
            due_year=due_year,
        )
    except ValueError:
        return None
    total = invoice_totals(db, invoice)
    if total <= 0:
        return None
    planned_count = db.scalar(
        select(func.count(Transaction.id)).where(
            Transaction.user_id == user_id,
            Transaction.invoice_id == invoice.id,
            Transaction.status == "planned",
        )
    )
    data = format_invoice(invoice, total)
    data["card_name"] = card.name
    data["planned_count"] = int(planned_count or 0)
    if card.settlement_account_id:
        settlement = db.get(Account, card.settlement_account_id)
        if settlement and settlement.is_active:
            data["settlement_account_name"] = settlement.name
    return data


def format_invoice_label(invoice: CardInvoice) -> str:
    return f"Fatura · {invoice.due_date.strftime('%d/%m')}"


def format_invoice(invoice: CardInvoice, total_cents: int) -> dict:
    return {
        "id": invoice.id,
        "card_id": invoice.card_id,
        "cycle_start": invoice.cycle_start.isoformat(),
        "cycle_end": invoice.cycle_end.isoformat(),
        "due_date": invoice.due_date.isoformat(),
        "due_date_label": invoice.due_date.strftime("%d/%m/%Y"),
        "status": invoice.status,
        "status_label": STATUS_LABELS.get(invoice.status, invoice.status),
        "total_cents": total_cents,
        "total": format_brl(total_cents),
        "invoice_label": format_invoice_label(invoice),
    }


def format_credit_card(card: CreditCard, db: Session | None = None) -> dict:
    data = {
        "id": card.id,
        "name": card.name,
        "account": card.name,
        "institution": card.institution,
        "credit_limit_cents": card.credit_limit_cents,
        "credit_limit": (
            format_brl(card.credit_limit_cents)
            if card.credit_limit_cents is not None
            else None
        ),
        "closing_day": card.closing_day,
        "due_day": card.due_day,
        "settlement_account_id": card.settlement_account_id,
        "is_active": card.is_active,
    }
    if card.settlement_account_id and db is not None:
        account = db.get(Account, card.settlement_account_id)
        if account:
            data["settlement_account_name"] = account.name
    if db is not None:
        data.update(card_summary(db, card))
    return data


def card_summary(db: Session, card: CreditCard, *, today: date | None = None) -> dict:
    ensure_invoices_for_card(db, card, today=today)
    today = today or local_today()
    used = unpaid_invoice_total(db, card.id)
    available = None
    if card.credit_limit_cents is not None:
        available = max(0, int(card.credit_limit_cents) - used)
    current = db.scalar(
        select(CardInvoice)
        .where(
            CardInvoice.card_id == card.id,
            CardInvoice.status.in_(("open", "closed")),
        )
        .order_by(CardInvoice.due_date.asc())
        .limit(1)
    )
    summary: dict = {
        "unpaid_total_cents": used,
        "unpaid_total": format_brl(used),
        "available_limit_cents": available,
    }
    if available is not None:
        summary["available_limit"] = format_brl(available)
    if current:
        total = invoice_totals(db, current)
        summary["current_invoice_id"] = current.id
        summary["current_invoice_due"] = current.due_date.isoformat()
        summary["current_invoice_due_label"] = current.due_date.strftime("%d/%m/%Y")
        summary["current_invoice_total_cents"] = total
        summary["current_invoice_total"] = format_brl(total)
        summary["current_invoice_status"] = current.status
        summary["current_invoice_status_label"] = STATUS_LABELS.get(
            current.status, current.status
        )
        summary["current_invoice_overdue"] = (
            current.due_date < today and current.status != "paid"
        )
        summary["invoice_label"] = format_invoice_label(current)
    return summary


def list_credit_cards(db: Session, user_id: int) -> list[dict]:
    cards = db.scalars(
        select(CreditCard)
        .where(CreditCard.user_id == user_id, CreditCard.is_active.is_(True))
        .order_by(CreditCard.name.asc())
    ).all()
    return [format_credit_card(card, db=db) for card in cards]


def _empty_invoice_dashboard() -> dict:
    return {
        "cards": [],
        "unpaid_count": 0,
        "unpaid_total_cents": 0,
        "unpaid_total": format_brl(0),
        "due_in_period_count": 0,
        "due_in_period_cents": 0,
        "due_in_period": format_brl(0),
    }


def invoice_dashboard(
    db: Session,
    user_id: int | None,
    *,
    period_start: date | None = None,
    period_end: date | None = None,
    today: date | None = None,
) -> dict:
    """Snapshot de faturas para o dashboard. Não altera receitas/despesas nem saldo bancário."""
    if user_id is None:
        return _empty_invoice_dashboard()

    today = today or local_today()
    sync_credit_cards(db, user_id, today=today)
    cards = list_credit_cards(db, user_id)
    unpaid_total = 0
    unpaid_count = 0
    due_in_period_cents = 0
    due_in_period_count = 0
    for card in cards:
        unpaid_cents = int(card.get("unpaid_total_cents") or 0)
        unpaid_total += unpaid_cents
        if unpaid_cents > 0:
            unpaid_count += 1
        due_raw = card.get("current_invoice_due")
        due_in_period = False
        if due_raw and period_start and period_end:
            due_d = date.fromisoformat(due_raw)
            current_cents = int(card.get("current_invoice_total_cents") or 0)
            due_in_period = period_start <= due_d <= period_end
            if due_in_period and current_cents > 0:
                due_in_period_count += 1
                due_in_period_cents += current_cents
        card["due_in_period"] = due_in_period
    return {
        "cards": cards,
        "unpaid_count": unpaid_count,
        "unpaid_total_cents": unpaid_total,
        "unpaid_total": format_brl(unpaid_total),
        "due_in_period_count": due_in_period_count,
        "due_in_period_cents": due_in_period_cents,
        "due_in_period": format_brl(due_in_period_cents),
    }


def list_invoices(
    db: Session,
    user_id: int,
    *,
    card_name: str | None = None,
    account_name: str | None = None,
    limit: int = 12,
) -> list[dict]:
    from app.services.finance import resolve_card_for_transaction

    name = card_name or account_name
    stmt = (
        select(CardInvoice)
        .join(CreditCard, CardInvoice.card_id == CreditCard.id)
        .where(CardInvoice.user_id == user_id)
        .order_by(CardInvoice.due_date.desc())
        .limit(limit)
    )
    if name and name.strip():
        card = resolve_card_for_transaction(db, user_id, name.strip())
        stmt = stmt.where(CardInvoice.card_id == card.id)

    results = []
    for inv in db.scalars(stmt).unique().all():
        card = inv.card if inv.card else db.get(CreditCard, inv.card_id)
        item = format_invoice(inv, invoice_totals(db, inv))
        item["card_name"] = card.name if card else None
        item["account_name"] = card.name if card else None
        if card:
            item["settlement_account_id"] = card.settlement_account_id
            if card.settlement_account_id:
                settlement = db.get(Account, card.settlement_account_id)
                if settlement:
                    item["settlement_account_name"] = settlement.name
        results.append(item)
    return results


def pay_invoice(
    db: Session,
    user_id: int,
    *,
    invoice_id: int | None = None,
    card_name: str | None = None,
    account_name: str | None = None,
    from_account_name: str,
    payment_date: date | None = None,
    due_month: int | None = None,
    due_year: int | None = None,
) -> dict:
    from app.services.finance import register_expense, resolve_account_for_transaction

    invoice, card = resolve_payable_invoice(
        db,
        user_id,
        invoice_id=invoice_id,
        card_name=card_name or account_name,
        due_month=due_month,
        due_year=due_year,
    )
    if invoice.status == "paid":
        raise ValueError("Esta fatura já foi paga.")

    from_account = resolve_account_for_transaction(db, user_id, from_account_name.strip())

    total = invoice_totals(db, invoice)
    if total <= 0:
        raise ValueError("Fatura sem valor a pagar.")

    pay_date = payment_date or local_today()
    settled = settle_invoice_planned_transactions(db, user_id, invoice, pay_date)
    payment = register_expense(
        db,
        user_id,
        RegisterExpenseInput(
            amount=format_brl(total),
            description=f"Pagamento fatura {card.name} {invoice.due_date.strftime('%d/%m/%Y')}",
            account_name=from_account.name,
            category_name="Outros",
            payment_date=pay_date,
            transaction_date=pay_date,
            competence_date=pay_date,
            due_date=pay_date,
        ),
    )

    invoice.status = "paid"
    invoice.paid_at = pay_date
    invoice.paid_from_account_id = from_account.id
    invoice.payment_transfer_group_id = str(payment.get("id"))
    db.commit()
    db.refresh(invoice)

    return {
        "invoice": {**format_invoice(invoice, total), "card_name": card.name, "account_name": card.name},
        "payment": payment,
        "settled_count": len(settled),
        "from_account_name": from_account.name,
    }
