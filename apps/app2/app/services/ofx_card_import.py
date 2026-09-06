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

from app.models import Account, CardInvoice, CreditCard, OfxImportBatch, OfxImportLine, Transaction
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

    return "skip", None, None


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
    if match is not None:
        used_tx_ids.add(match.id)
        return "match", match.id, None
    return "create", None, None


def create_batch(
    db: Session,
    user_id: int,
    card: CreditCard,
    filename: str,
    content: str | bytes,
) -> OfxImportBatch:
    expire_stale_batches(db, user_id)
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
        if action == "already_imported":
            # keep known set accurate within batch
            pass
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
            chosen_action=action,
            chosen_transaction_id=tx_id,
            chosen_invoice_id=inv_id,
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


def _unpaid_invoices_near_amount(
    db: Session,
    user_id: int,
    card_id: int,
    amount_cents: int,
) -> list[CardInvoice]:
    from app.services.credit_cards import invoice_totals

    invoices = list(
        db.scalars(
            select(CardInvoice).where(
                CardInvoice.user_id == user_id,
                CardInvoice.card_id == card_id,
                CardInvoice.status.in_(("open", "closed")),
            )
        ).all()
    )
    matched = [
        inv
        for inv in invoices
        if abs(invoice_totals(db, inv) - amount_cents) <= AMOUNT_TOLERANCE_CENTS
    ]
    matched.sort(key=lambda inv: inv.due_date)
    return matched


def line_review_payload(
    db: Session,
    user_id: int,
    card_id: int,
    line: OfxImportLine,
) -> dict[str, Any]:
    from app.services.credit_cards import format_invoice, invoice_totals
    from app.schemas import format_brl as brl

    payload: dict[str, Any] = {
        "id": line.id,
        "fitid": line.fitid,
        "posted_date": line.posted_date.isoformat(),
        "amount_cents": line.amount_cents,
        "amount": brl(line.amount_cents),
        "direction": line.direction,
        "memo": line.memo,
        "suggested_action": line.suggested_action,
        "chosen_action": line.chosen_action or line.suggested_action,
        "chosen_transaction_id": line.chosen_transaction_id or line.suggested_transaction_id,
        "chosen_invoice_id": line.chosen_invoice_id or line.suggested_invoice_id,
        "candidates": [],
        "invoice_options": [],
    }
    if line.direction == "debit":
        for tx in _match_candidates_for_line(db, user_id, card_id, line):
            payload["candidates"].append(
                {
                    "id": tx.id,
                    "description": tx.description,
                    "status": tx.status,
                    "competence_date": tx.competence_date.isoformat(),
                    "score": round(description_score(line.memo, tx.description), 2),
                }
            )
    else:
        for inv in _unpaid_invoices_near_amount(db, user_id, card_id, line.amount_cents):
            total = invoice_totals(db, inv)
            payload["invoice_options"].append(format_invoice(inv, total))
        # Also include suggested paid invoice if linking
        if line.suggested_invoice_id:
            inv = db.get(CardInvoice, line.suggested_invoice_id)
            if inv and inv.user_id == user_id:
                total = invoice_totals(db, inv)
                opt = format_invoice(inv, total)
                if not any(o["id"] == opt["id"] for o in payload["invoice_options"]):
                    payload["invoice_options"].append(opt)
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
            "skip": sum(1 for ln in lines if ln["suggested_action"] == "skip"),
            "already_imported": sum(
                1 for ln in lines if ln["suggested_action"] == "already_imported"
            ),
        },
    }


def _parse_choice_action(raw: str | None, fallback: str) -> Action:
    allowed: set[str] = {
        "create",
        "match",
        "pay_invoice",
        "link_invoice_payment",
        "skip",
        "already_imported",
    }
    value = (raw or fallback or "skip").strip()
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
        action = _parse_choice_action(choice.get("action"), line.chosen_action or line.suggested_action)
        tx_id = choice.get("transaction_id")
        inv_id = choice.get("invoice_id")
        if tx_id is not None and tx_id != "":
            tx_id = int(tx_id)
        else:
            tx_id = line.chosen_transaction_id or line.suggested_transaction_id
        if inv_id is not None and inv_id != "":
            inv_id = int(inv_id)
        else:
            inv_id = line.chosen_invoice_id or line.suggested_invoice_id

        line.chosen_action = action
        line.chosen_transaction_id = tx_id if action == "match" else None
        line.chosen_invoice_id = inv_id if action in ("pay_invoice", "link_invoice_payment") else None

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
            from app.services.credit_cards import invoice_due_for_purchase

            due = invoice_due_for_purchase(card, line.posted_date)
            finance.create_transaction(
                db,
                user_id,
                TransactionCreate(
                    card_id=card.id,
                    type="expense",
                    amount_cents=line.amount_cents,
                    description=line.memo or "Compra cartão",
                    competence_date=line.posted_date,
                    due_date=due,
                    status="planned",
                    ofx_fitid=line.fitid,
                ),
            )
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
            tx.ofx_fitid = line.fitid
            db.commit()
            summary["matched"] += 1
            continue

        if action == "pay_invoice":
            if not inv_id:
                raise ValueError(f"Selecione a fatura para pagamento ({line.memo}).")
            if not card.settlement_account_id:
                raise ValueError("Cartão sem conta de liquidação.")
            settlement = db.get(Account, card.settlement_account_id)
            if settlement is None or settlement.user_id != user_id:
                raise ValueError("Conta de liquidação inválida.")
            result = pay_invoice(
                db,
                user_id,
                invoice_id=inv_id,
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
            if not inv_id:
                raise ValueError("Fatura inválida para vínculo.")
            inv = db.get(CardInvoice, inv_id)
            if inv is None or inv.user_id != user_id or inv.card_id != card.id:
                raise ValueError("Fatura inválida.")
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
