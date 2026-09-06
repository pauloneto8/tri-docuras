"""Importação OFX de cartão de crédito: parse, matching e aplicação."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Account,
    CardInvoice,
    Category,
    CreditCard,
    OfxCategoryMemory,
    OfxImportBatch,
    OfxImportLine,
    Transaction,
)
from app.schemas import TransactionCreate
from app.timezone import local_now

Direction = Literal["debit", "credit"]
Action = Literal[
    "create",
    "match",
    "pay_invoice",
    "link_invoice_payment",
    "skip",
    "already_imported",
    "pending",
]

DATE_WINDOW_DAYS = 3
PAYMENT_DATE_WINDOW_DAYS = 5
MATCH_SCORE_THRESHOLD = 0.45
BATCH_TTL_HOURS = 24
AMOUNT_TOLERANCE_CENTS = 1

_STMTTRN_RE = re.compile(r"<STMTTRN>(.*?)</STMTTRN>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(
    r"<(FITID|DTPOSTED|TRNAMT|TRNTYPE|MEMO|NAME|CHECKNUM)>([^<\r\n]+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class OfxTxn:
    fitid: str
    posted_date: date
    amount_cents: int
    direction: Direction
    memo: str
    trntype: str


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_memo(text: str) -> str:
    cleaned = _strip_accents(text or "").lower()
    cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _parse_ofx_date(raw: str) -> date:
    digits = re.sub(r"[^0-9]", "", raw.strip())
    if len(digits) < 8:
        raise ValueError(f"Data OFX inválida: {raw!r}")
    return date(int(digits[0:4]), int(digits[4:6]), int(digits[6:8]))


def _parse_amount_to_cents(raw: str) -> int:
    text = raw.strip().replace(" ", "")
    if not text:
        raise ValueError("Valor OFX vazio.")
    negative = text.startswith("-")
    text = text.lstrip("+-")
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    value = float(text)
    cents = int(round(abs(value) * 100))
    return -cents if negative or value < 0 else cents


def _direction_from_amount_and_type(signed_cents: int, trntype: str) -> Direction:
    t = (trntype or "").upper()
    if t in {"CREDIT", "DEP", "DIRECTDEP", "PAYMENT", "XFER"} and signed_cents > 0:
        return "credit"
    if t in {"DEBIT", "POS", "ATM", "CHECK", "FEE", "SRVCHG"} and signed_cents < 0:
        return "debit"
    if signed_cents < 0:
        return "debit"
    if signed_cents > 0:
        return "credit"
    return "debit"


def parse_ofx(content: str | bytes) -> list[OfxTxn]:
    if isinstance(content, bytes):
        for encoding in ("utf-8", "latin-1", "cp1252"):
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            text = content.decode("utf-8", errors="replace")
    else:
        text = content

    text = text.replace("\x00", "")
    # Normalize self-closing / XML end tags for tag extraction
    blocks = _STMTTRN_RE.findall(text)
    if not blocks:
        # OFX 1.x sometimes omits closing STMTTRN; split by opening tag
        parts = re.split(r"<STMTTRN>", text, flags=re.IGNORECASE)
        blocks = parts[1:] if len(parts) > 1 else []

    txns: list[OfxTxn] = []
    seen_fitids: set[str] = set()
    for block in blocks:
        fields: dict[str, str] = {}
        for match in _TAG_RE.finditer(block):
            fields[match.group(1).upper()] = match.group(2).strip()
        fitid = fields.get("FITID") or fields.get("CHECKNUM")
        if not fitid:
            continue
        if fitid in seen_fitids:
            continue
        raw_date = fields.get("DTPOSTED")
        raw_amt = fields.get("TRNAMT")
        if not raw_date or raw_amt is None:
            continue
        signed = _parse_amount_to_cents(raw_amt)
        if signed == 0:
            continue
        trntype = fields.get("TRNTYPE", "")
        direction = _direction_from_amount_and_type(signed, trntype)
        memo = (fields.get("MEMO") or fields.get("NAME") or "Movimento OFX").strip()[:255]
        seen_fitids.add(fitid)
        txns.append(
            OfxTxn(
                fitid=fitid[:128],
                posted_date=_parse_ofx_date(raw_date),
                amount_cents=abs(signed),
                direction=direction,
                memo=memo,
                trntype=trntype.upper(),
            )
        )
    if not txns:
        raise ValueError("Nenhuma transação encontrada no arquivo OFX.")
    return txns


def description_score(a: str, b: str) -> float:
    na, nb = normalize_memo(a), normalize_memo(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.85
    return SequenceMatcher(None, na, nb).ratio()


def expire_stale_batches(db: Session, user_id: int | None = None) -> int:
    cutoff = local_now() - timedelta(hours=BATCH_TTL_HOURS)
    q = select(OfxImportBatch).where(
        OfxImportBatch.status == "pending",
        OfxImportBatch.created_at < cutoff,
    )
    if user_id is not None:
        q = q.where(OfxImportBatch.user_id == user_id)
    batches = list(db.scalars(q).all())
    for batch in batches:
        batch.status = "cancelled"
    if batches:
        db.commit()
    return len(batches)


def _existing_fitids(db: Session, user_id: int) -> set[str]:
    rows = db.scalars(
        select(Transaction.ofx_fitid).where(
            Transaction.user_id == user_id,
            Transaction.ofx_fitid.is_not(None),
        )
    ).all()
    return {f for f in rows if f}


def _card_transactions(db: Session, user_id: int, card_id: int) -> list[Transaction]:
    return list(
        db.scalars(
            select(Transaction).where(
                Transaction.user_id == user_id,
                Transaction.card_id == card_id,
                Transaction.type == "expense",
                Transaction.ofx_fitid.is_(None),
            )
        ).all()
    )


def _best_debit_match(
    txn: OfxTxn,
    candidates: list[Transaction],
    used_ids: set[int],
) -> tuple[Transaction | None, float]:
    best: Transaction | None = None
    best_score = 0.0
    for tx in candidates:
        if tx.id in used_ids:
            continue
        if tx.amount_cents != txn.amount_cents:
            continue
        dates = [tx.competence_date, tx.transaction_date, tx.due_date]
        if not any(
            d is not None and abs((d - txn.posted_date).days) <= DATE_WINDOW_DAYS for d in dates
        ):
            continue
        score = description_score(txn.memo, tx.description)
        # Prefer planned when scores are close
        if tx.status == "planned":
            score += 0.05
        if score > best_score:
            best_score = score
            best = tx
    if best is None or best_score < MATCH_SCORE_THRESHOLD:
        return None, best_score
    return best, best_score


def _invoice_payment_suggestion(
    db: Session,
    user_id: int,
    card: CreditCard,
    txn: OfxTxn,
) -> tuple[Action, int | None, int | None]:
    invoices = list(
        db.scalars(
            select(CardInvoice).where(
                CardInvoice.user_id == user_id,
                CardInvoice.card_id == card.id,
            )
        ).all()
    )
    from app.services.credit_cards import invoice_totals

    unpaid_matches: list[tuple[CardInvoice, int]] = []
    paid_matches: list[tuple[CardInvoice, int]] = []
    for inv in invoices:
        total = invoice_totals(db, inv)
        if total <= 0:
            continue
        if abs(total - txn.amount_cents) > AMOUNT_TOLERANCE_CENTS:
            continue
        if inv.status in ("open", "closed"):
            unpaid_matches.append((inv, total))
        elif inv.status == "paid" and inv.paid_at is not None:
            if abs((inv.paid_at - txn.posted_date).days) <= PAYMENT_DATE_WINDOW_DAYS:
                paid_matches.append((inv, total))

    if unpaid_matches:
        # Prefer invoice whose due_date is closest to posted date
        unpaid_matches.sort(key=lambda item: abs((item[0].due_date - txn.posted_date).days))
        inv = unpaid_matches[0][0]
        return "pay_invoice", None, inv.id

    if paid_matches:
        paid_matches.sort(key=lambda item: abs((item[0].paid_at - txn.posted_date).days))  # type: ignore[operator]
        inv = paid_matches[0][0]
        payment_tx_id = None
        if inv.payment_transfer_group_id and inv.payment_transfer_group_id.isdigit():
            payment_tx_id = int(inv.payment_transfer_group_id)
        return "link_invoice_payment", payment_tx_id, inv.id

    # Nunca ignorar automaticamente — usuário confirma na revisão
    return "pending", None, None


def _suggested_invoice_for_purchase(
    db: Session, card: CreditCard, posted_date: date
) -> int:
    from app.services.credit_cards import get_or_create_invoice

    return get_or_create_invoice(db, card, posted_date).id


def memo_key(memo: str) -> str:
    return normalize_memo(memo)[:255]


def lookup_category_memory(db: Session, user_id: int, memo: str) -> int | None:
    key = memo_key(memo)
    if not key:
        return None
    row = db.scalar(
        select(OfxCategoryMemory).where(
            OfxCategoryMemory.user_id == user_id,
            OfxCategoryMemory.memo_key == key,
        )
    )
    if row is None:
        return None
    cat = db.get(Category, row.category_id)
    if cat is None or cat.user_id != user_id:
        return None
    return cat.id


def remember_category(db: Session, user_id: int, memo: str, category_id: int) -> None:
    key = memo_key(memo)
    if not key:
        return
    cat = db.get(Category, category_id)
    if cat is None or cat.user_id != user_id:
        raise ValueError("Categoria inválida.")
    row = db.scalar(
        select(OfxCategoryMemory).where(
            OfxCategoryMemory.user_id == user_id,
            OfxCategoryMemory.memo_key == key,
        )
    )
    if row is None:
        db.add(
            OfxCategoryMemory(
                user_id=user_id,
                memo_key=key,
                category_id=category_id,
            )
        )
    else:
        row.category_id = category_id
    db.flush()


def suggest_category_id(
    db: Session,
    user_id: int,
    memo: str,
    *,
    matched_tx: Transaction | None = None,
    tx_type: str = "expense",
) -> int | None:
    """Ordem: memória OFX → categoria do lançamento conciliado → keywords."""
    memorized = lookup_category_memory(db, user_id, memo)
    if memorized is not None:
        return memorized
    if matched_tx is not None and matched_tx.category_id is not None:
        return matched_tx.category_id
    from app.services.finance import suggest_category_by_keywords

    suggested = suggest_category_by_keywords(db, user_id, memo, tx_type)
    return suggested.id if suggested else None


def _resolve_category(
    db: Session,
    user_id: int,
    category_id: int | None,
    *,
    memo: str,
) -> int | None:
    if category_id is None:
        return None
    cat = db.get(Category, category_id)
    if cat is None or cat.user_id != user_id:
        raise ValueError(f"Categoria inválida para o lançamento ({memo}).")
    return cat.id


def _expense_categories(db: Session, user_id: int) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(Category)
        .where(Category.user_id == user_id, Category.type == "expense")
        .order_by(Category.name.asc())
    ).all()
    return [{"id": c.id, "name": c.name} for c in rows]


def suggest_for_txn(
    db: Session,
    user_id: int,
    card: CreditCard,
    txn: OfxTxn,
    *,
    known_fitids: set[str],
    card_txs: list[Transaction],
    used_tx_ids: set[int],
) -> tuple[Action, int | None, int | None]:
    if txn.fitid in known_fitids:
        return "already_imported", None, None

    if txn.direction == "credit":
        return _invoice_payment_suggestion(db, user_id, card, txn)

    match, _score = _best_debit_match(txn, card_txs, used_tx_ids)
    inv_id = _suggested_invoice_for_purchase(db, card, txn.posted_date)
    if match is not None:
        used_tx_ids.add(match.id)
        return "match", match.id, match.invoice_id or inv_id
    return "create", None, inv_id


def create_batch(
    db: Session,
    user_id: int,
    card: CreditCard,
    filename: str,
    content: str | bytes,
) -> OfxImportBatch:
    from app.services.credit_cards import ensure_invoices_for_card

    expire_stale_batches(db, user_id)
    ensure_invoices_for_card(db, card)
    txns = parse_ofx(content)
    known = _existing_fitids(db, user_id)
    card_txs = _card_transactions(db, user_id, card.id)
    used_tx_ids: set[int] = set()

    batch = OfxImportBatch(
        user_id=user_id,
        card_id=card.id,
        filename=(filename or "extrato.ofx")[:255],
        status="pending",
    )
    db.add(batch)
    db.flush()

    for txn in txns:
        action, tx_id, inv_id = suggest_for_txn(
            db,
            user_id,
            card,
            txn,
            known_fitids=known,
            card_txs=card_txs,
            used_tx_ids=used_tx_ids,
        )
        matched_tx = None
        if tx_id is not None:
            matched_tx = next((t for t in card_txs if t.id == tx_id), None)
            if matched_tx is None:
                matched_tx = db.get(Transaction, tx_id)
        cat_id = None
        if txn.direction == "debit" and action not in ("already_imported",):
            cat_id = suggest_category_id(
                db, user_id, txn.memo, matched_tx=matched_tx, tx_type="expense"
            )
        # pending: sem ação pré-escolhida — exige confirmação na UI
        chosen = None if action == "pending" else action
        line = OfxImportLine(
            batch_id=batch.id,
            fitid=txn.fitid,
            posted_date=txn.posted_date,
            amount_cents=txn.amount_cents,
            direction=txn.direction,
            memo=txn.memo,
            suggested_action=action,
            suggested_transaction_id=tx_id,
            suggested_invoice_id=inv_id,
            suggested_category_id=cat_id,
            chosen_action=chosen,
            chosen_transaction_id=tx_id if chosen else None,
            chosen_invoice_id=inv_id if chosen else inv_id,
            chosen_category_id=cat_id,
        )
        db.add(line)

    db.commit()
    db.refresh(batch)
    return get_batch(db, user_id, card.id, batch.id)


def get_batch(
    db: Session,
    user_id: int,
    card_id: int,
    batch_id: int,
) -> OfxImportBatch:
    batch = db.scalar(
        select(OfxImportBatch)
        .options(
            selectinload(OfxImportBatch.lines).selectinload(OfxImportLine.suggested_transaction),
            selectinload(OfxImportBatch.lines).selectinload(OfxImportLine.suggested_invoice),
            selectinload(OfxImportBatch.lines).selectinload(OfxImportLine.chosen_transaction),
            selectinload(OfxImportBatch.lines).selectinload(OfxImportLine.chosen_invoice),
        )
        .where(
            OfxImportBatch.id == batch_id,
            OfxImportBatch.user_id == user_id,
            OfxImportBatch.card_id == card_id,
        )
    )
    if batch is None:
        raise ValueError("Lote de importação não encontrado.")
    return batch


def cancel_batch(db: Session, user_id: int, card_id: int, batch_id: int) -> None:
    batch = get_batch(db, user_id, card_id, batch_id)
    if batch.status != "pending":
        raise ValueError("Este lote já foi finalizado.")
    batch.status = "cancelled"
    db.commit()


def _match_candidates_for_line(
    db: Session,
    user_id: int,
    card_id: int,
    line: OfxImportLine,
) -> list[Transaction]:
    window_start = line.posted_date - timedelta(days=DATE_WINDOW_DAYS)
    window_end = line.posted_date + timedelta(days=DATE_WINDOW_DAYS)
    rows = list(
        db.scalars(
            select(Transaction).where(
                Transaction.user_id == user_id,
                Transaction.card_id == card_id,
                Transaction.type == "expense",
                Transaction.amount_cents == line.amount_cents,
                Transaction.ofx_fitid.is_(None),
            )
        ).all()
    )
    out: list[Transaction] = []
    for tx in rows:
        dates = [tx.competence_date, tx.transaction_date, tx.due_date]
        if any(d is not None and window_start <= d <= window_end for d in dates):
            out.append(tx)
    out.sort(
        key=lambda tx: (
            0 if tx.status == "planned" else 1,
            -description_score(line.memo, tx.description),
            tx.id,
        )
    )
    return out


def _all_card_invoices(
    db: Session,
    user_id: int,
    card_id: int,
) -> list[CardInvoice]:
    return list(
        db.scalars(
            select(CardInvoice)
            .where(
                CardInvoice.user_id == user_id,
                CardInvoice.card_id == card_id,
            )
            .order_by(CardInvoice.due_date.desc())
        ).all()
    )


def _resolve_invoice(
    db: Session,
    user_id: int,
    card: CreditCard,
    invoice_id: int | None,
    *,
    memo: str,
) -> CardInvoice:
    if not invoice_id:
        raise ValueError(f"Selecione a fatura para o lançamento ({memo}).")
    inv = db.get(CardInvoice, invoice_id)
    if inv is None or inv.user_id != user_id or inv.card_id != card.id:
        raise ValueError(f"Fatura inválida para o lançamento ({memo}).")
    return inv


def line_review_payload(
    db: Session,
    user_id: int,
    card_id: int,
    line: OfxImportLine,
) -> dict[str, Any]:
    from app.services.credit_cards import format_invoice, invoice_totals
    from app.schemas import format_brl as brl

    chosen = line.chosen_action or (
        None if line.suggested_action == "pending" else line.suggested_action
    )
    payload: dict[str, Any] = {
        "id": line.id,
        "fitid": line.fitid,
        "posted_date": line.posted_date.isoformat(),
        "amount_cents": line.amount_cents,
        "amount": brl(line.amount_cents),
        "direction": line.direction,
        "memo": line.memo,
        "suggested_action": line.suggested_action,
        "chosen_action": chosen,
        "chosen_transaction_id": line.chosen_transaction_id or line.suggested_transaction_id,
        "chosen_invoice_id": line.chosen_invoice_id or line.suggested_invoice_id,
        "chosen_category_id": line.chosen_category_id or line.suggested_category_id,
        "candidates": [],
        "invoice_options": [],
        "category_options": _expense_categories(db, user_id) if line.direction == "debit" else [],
        "requires_confirmation": line.suggested_action
        in ("pending", "skip")
        or line.chosen_action is None,
    }
    for inv in _all_card_invoices(db, user_id, card_id):
        total = invoice_totals(db, inv)
        payload["invoice_options"].append(format_invoice(inv, total))

    if line.direction == "debit":
        for tx in _match_candidates_for_line(db, user_id, card_id, line):
            payload["candidates"].append(
                {
                    "id": tx.id,
                    "description": tx.description,
                    "status": tx.status,
                    "competence_date": tx.competence_date.isoformat(),
                    "invoice_id": tx.invoice_id,
                    "score": round(description_score(line.memo, tx.description), 2),
                }
            )
    return payload


def batch_review_context(db: Session, batch: OfxImportBatch) -> dict[str, Any]:
    lines = [
        line_review_payload(db, batch.user_id, batch.card_id, line) for line in batch.lines
    ]
    return {
        "batch_id": batch.id,
        "filename": batch.filename,
        "status": batch.status,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
        "lines": lines,
        "counts": {
            "total": len(lines),
            "create": sum(1 for ln in lines if ln["suggested_action"] == "create"),
            "match": sum(1 for ln in lines if ln["suggested_action"] == "match"),
            "pay_invoice": sum(1 for ln in lines if ln["suggested_action"] == "pay_invoice"),
            "link_invoice_payment": sum(
                1 for ln in lines if ln["suggested_action"] == "link_invoice_payment"
            ),
            "pending": sum(1 for ln in lines if ln["suggested_action"] == "pending"),
            "skip": sum(1 for ln in lines if ln["suggested_action"] == "skip"),
            "already_imported": sum(
                1 for ln in lines if ln["suggested_action"] == "already_imported"
            ),
        },
    }


def _parse_choice_action(raw: str | None, fallback: str | None) -> Action:
    allowed: set[str] = {
        "create",
        "match",
        "pay_invoice",
        "link_invoice_payment",
        "skip",
        "already_imported",
    }
    value = (raw if raw is not None and str(raw).strip() != "" else (fallback or "")).strip()
    if not value or value == "pending":
        raise ValueError(
            "Confirme a ação de cada lançamento — nenhum movimento é ignorado automaticamente."
        )
    if value not in allowed:
        raise ValueError(f"Ação inválida: {value}")
    return value  # type: ignore[return-value]


def apply_batch(
    db: Session,
    user_id: int,
    card: CreditCard,
    batch_id: int,
    choices: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    from app.services import finance
    from app.services.credit_cards import pay_invoice

    batch = get_batch(db, user_id, card.id, batch_id)
    if batch.status != "pending":
        raise ValueError("Este lote já foi finalizado.")

    # Expire check
    created = batch.created_at
    if created is not None:
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if local_now() - created > timedelta(hours=BATCH_TTL_HOURS):
            batch.status = "cancelled"
            db.commit()
            raise ValueError("Lote expirado. Envie o OFX novamente.")

    summary = {
        "created": 0,
        "matched": 0,
        "payments": 0,
        "linked_payments": 0,
        "skipped": 0,
        "already_imported": 0,
    }

    for line in batch.lines:
        choice = choices.get(line.id, {})
        # Já importado: permite confirmar sem reprocessar
        if line.suggested_action == "already_imported" and not choice.get("action"):
            action: Action = "already_imported"
        else:
            # skip só vale se veio explicitamente no formulário (ou chosen já era skip confirmado)
            raw_action = choice.get("action")
            if raw_action is None or str(raw_action).strip() == "":
                # Sem escolha no form: usa chosen apenas se não for skip implícito de pending
                fallback = line.chosen_action
                if fallback == "skip" and "action" not in choice:
                    raise ValueError(
                        f"Confirme se deseja ignorar: {line.memo} ({line.posted_date})."
                    )
                action = _parse_choice_action(None, fallback)
            else:
                action = _parse_choice_action(str(raw_action), None)

        tx_id = choice.get("transaction_id")
        inv_id = choice.get("invoice_id")
        cat_id = choice.get("category_id")
        if tx_id is not None and tx_id != "":
            tx_id = int(tx_id)
        else:
            tx_id = line.chosen_transaction_id or line.suggested_transaction_id
        if inv_id is not None and inv_id != "":
            inv_id = int(inv_id)
        else:
            inv_id = line.chosen_invoice_id or line.suggested_invoice_id
        if cat_id is not None and cat_id != "":
            cat_id = int(cat_id)
        else:
            cat_id = line.chosen_category_id or line.suggested_category_id

        line.chosen_action = action
        line.chosen_transaction_id = tx_id if action == "match" else None
        line.chosen_invoice_id = (
            inv_id
            if action in ("create", "match", "pay_invoice", "link_invoice_payment")
            else None
        )
        line.chosen_category_id = (
            cat_id if action in ("create", "match") else None
        )

        if action in ("skip", "already_imported"):
            summary["skipped" if action == "skip" else "already_imported"] += 1
            continue

        # Idempotent if fitid already exists
        existing = db.scalar(
            select(Transaction).where(
                Transaction.user_id == user_id,
                Transaction.ofx_fitid == line.fitid,
            )
        )
        if existing is not None:
            line.chosen_action = "already_imported"
            summary["already_imported"] += 1
            continue

        if action == "create":
            if line.direction != "debit":
                raise ValueError("Só é possível criar compra a partir de débito OFX.")
            inv = _resolve_invoice(db, user_id, card, inv_id, memo=line.memo)
            resolved_cat = _resolve_category(db, user_id, cat_id, memo=line.memo)
            finance.create_transaction(
                db,
                user_id,
                TransactionCreate(
                    card_id=card.id,
                    category_id=resolved_cat,
                    type="expense",
                    amount_cents=line.amount_cents,
                    description=line.memo or "Compra cartão",
                    competence_date=line.posted_date,
                    due_date=inv.due_date,
                    status="planned",
                    invoice_id=inv.id,
                    ofx_fitid=line.fitid,
                ),
            )
            if resolved_cat is not None:
                remember_category(db, user_id, line.memo, resolved_cat)
                db.commit()
            summary["created"] += 1
            continue

        if action == "match":
            if not tx_id:
                raise ValueError(f"Selecione o lançamento para conciliar ({line.memo}).")
            tx = db.get(Transaction, tx_id)
            if (
                tx is None
                or tx.user_id != user_id
                or tx.card_id != card.id
                or tx.amount_cents != line.amount_cents
            ):
                raise ValueError("Lançamento inválido para conciliação.")
            if tx.ofx_fitid and tx.ofx_fitid != line.fitid:
                raise ValueError("Lançamento já conciliado com outro FITID.")
            inv = _resolve_invoice(db, user_id, card, inv_id, memo=line.memo)
            resolved_cat = _resolve_category(db, user_id, cat_id, memo=line.memo)
            tx.ofx_fitid = line.fitid
            tx.invoice_id = inv.id
            if resolved_cat is not None:
                tx.category_id = resolved_cat
                remember_category(db, user_id, line.memo, resolved_cat)
            db.commit()
            summary["matched"] += 1
            continue

        if action == "pay_invoice":
            inv = _resolve_invoice(db, user_id, card, inv_id, memo=line.memo)
            if not card.settlement_account_id:
                raise ValueError("Cartão sem conta de liquidação.")
            settlement = db.get(Account, card.settlement_account_id)
            if settlement is None or settlement.user_id != user_id:
                raise ValueError("Conta de liquidação inválida.")
            result = pay_invoice(
                db,
                user_id,
                invoice_id=inv.id,
                from_account_name=settlement.name,
                payment_date=line.posted_date,
            )
            payment_id = result.get("payment", {}).get("id")
            if payment_id:
                pay_tx = db.get(Transaction, int(payment_id))
                if pay_tx is not None:
                    pay_tx.ofx_fitid = line.fitid
                    db.commit()
            summary["payments"] += 1
            continue

        if action == "link_invoice_payment":
            inv = _resolve_invoice(db, user_id, card, inv_id, memo=line.memo)
            pay_tx = None
            if inv.payment_transfer_group_id and str(inv.payment_transfer_group_id).isdigit():
                pay_tx = db.get(Transaction, int(inv.payment_transfer_group_id))
            if pay_tx is None and tx_id:
                pay_tx = db.get(Transaction, tx_id)
            if pay_tx is None or pay_tx.user_id != user_id:
                raise ValueError("Pagamento da fatura não encontrado para vincular.")
            pay_tx.ofx_fitid = line.fitid
            db.commit()
            summary["linked_payments"] += 1
            continue

        raise ValueError(f"Ação não suportada: {action}")

    batch.status = "applied"
    db.commit()
    return summary


def format_apply_summary(summary: dict[str, int]) -> str:
    parts = []
    if summary.get("created"):
        parts.append(f"{summary['created']} criados")
    if summary.get("matched"):
        parts.append(f"{summary['matched']} conciliados")
    if summary.get("payments"):
        parts.append(f"{summary['payments']} pagamentos de fatura")
    if summary.get("linked_payments"):
        parts.append(f"{summary['linked_payments']} pagamentos vinculados")
    if summary.get("skipped"):
        parts.append(f"{summary['skipped']} ignorados")
    if summary.get("already_imported"):
        parts.append(f"{summary['already_imported']} já importados")
    if not parts:
        return "Nenhuma alteração aplicada."
    return "Importação concluída: " + ", ".join(parts) + "."
