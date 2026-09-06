"""Importação OFX de contas bancárias: parse, matching e aplicação."""

from __future__ import annotations

from datetime import timedelta, timezone
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Account, Category, OfxImportBatch, OfxImportLine, Transaction
from app.schemas import RealizePlannedInput, TransactionCreate, format_brl as brl
from app.services import ofx_card_import as ofx_common
from app.timezone import local_now

Direction = Literal["debit", "credit"]
Action = Literal["create", "match", "skip", "already_imported"]

DATE_WINDOW_DAYS = ofx_common.DATE_WINDOW_DAYS
MATCH_SCORE_THRESHOLD = ofx_common.MATCH_SCORE_THRESHOLD
BATCH_TTL_HOURS = ofx_common.BATCH_TTL_HOURS


def _tx_type_for_direction(direction: Direction) -> str:
    return "expense" if direction == "debit" else "income"


def _account_candidates(
    db: Session,
    user_id: int,
    account_id: int,
    *,
    tx_type: str,
) -> list[Transaction]:
    return list(
        db.scalars(
            select(Transaction).where(
                Transaction.user_id == user_id,
                Transaction.account_id == account_id,
                Transaction.card_id.is_(None),
                Transaction.type == tx_type,
                Transaction.ofx_fitid.is_(None),
            )
        ).all()
    )


def _best_match(
    txn: ofx_common.OfxTxn,
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
        dates = [tx.competence_date, tx.transaction_date, tx.due_date, tx.payment_date]
        if not any(
            d is not None and abs((d - txn.posted_date).days) <= DATE_WINDOW_DAYS for d in dates
        ):
            continue
        score = ofx_common.description_score(txn.memo, tx.description)
        if tx.status == "planned":
            score += 0.05
        if score > best_score:
            best_score = score
            best = tx
    if best is None or best_score < MATCH_SCORE_THRESHOLD:
        return None, best_score
    return best, best_score


def suggest_for_txn(
    db: Session,
    user_id: int,
    account_id: int,
    txn: ofx_common.OfxTxn,
    *,
    known_fitids: set[str],
    candidates: list[Transaction],
    used_tx_ids: set[int],
) -> tuple[Action, int | None]:
    if txn.fitid in known_fitids:
        return "already_imported", None
    match, _score = _best_match(txn, candidates, used_tx_ids)
    if match is not None:
        used_tx_ids.add(match.id)
        return "match", match.id
    return "create", None


def _categories_for_type(db: Session, user_id: int, tx_type: str) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(Category)
        .where(Category.user_id == user_id, Category.type == tx_type)
        .order_by(Category.name.asc())
    ).all()
    return [{"id": c.id, "name": c.name} for c in rows]


def create_batch(
    db: Session,
    user_id: int,
    account: Account,
    filename: str,
    content: str | bytes,
) -> OfxImportBatch:
    ofx_common.expire_stale_batches(db, user_id)
    txns = ofx_common.parse_statement(content, filename=filename)
    known = ofx_common._existing_fitids(db, user_id)
    expense_cands = _account_candidates(db, user_id, account.id, tx_type="expense")
    income_cands = _account_candidates(db, user_id, account.id, tx_type="income")
    used_tx_ids: set[int] = set()

    batch = OfxImportBatch(
        user_id=user_id,
        card_id=None,
        account_id=account.id,
        filename=(filename or "extrato.ofx")[:255],
        status="pending",
    )
    db.add(batch)
    db.flush()

    for txn in txns:
        tx_type = _tx_type_for_direction(txn.direction)
        cands = expense_cands if tx_type == "expense" else income_cands
        action, tx_id = suggest_for_txn(
            db,
            user_id,
            account.id,
            txn,
            known_fitids=known,
            candidates=cands,
            used_tx_ids=used_tx_ids,
        )
        matched_tx = None
        if tx_id is not None:
            matched_tx = next((t for t in cands if t.id == tx_id), None)
            if matched_tx is None:
                matched_tx = db.get(Transaction, tx_id)
        cat_id = None
        if action != "already_imported":
            cat_id = ofx_common.suggest_category_id(
                db, user_id, txn.memo, matched_tx=matched_tx, tx_type=tx_type
            )
        line = OfxImportLine(
            batch_id=batch.id,
            fitid=txn.fitid,
            posted_date=txn.posted_date,
            amount_cents=txn.amount_cents,
            direction=txn.direction,
            memo=txn.memo,
            suggested_action=action,
            suggested_transaction_id=tx_id,
            suggested_invoice_id=None,
            suggested_category_id=cat_id,
            chosen_action=action,
            chosen_transaction_id=tx_id if action == "match" else None,
            chosen_invoice_id=None,
            chosen_category_id=cat_id,
        )
        db.add(line)

    db.commit()
    db.refresh(batch)
    return get_batch(db, user_id, account.id, batch.id)


def get_batch(
    db: Session,
    user_id: int,
    account_id: int,
    batch_id: int,
) -> OfxImportBatch:
    batch = db.scalar(
        select(OfxImportBatch)
        .options(
            selectinload(OfxImportBatch.lines).selectinload(OfxImportLine.suggested_transaction),
            selectinload(OfxImportBatch.lines).selectinload(OfxImportLine.chosen_transaction),
        )
        .where(
            OfxImportBatch.id == batch_id,
            OfxImportBatch.user_id == user_id,
            OfxImportBatch.account_id == account_id,
        )
    )
    if batch is None:
        raise ValueError("Lote de importação não encontrado.")
    return batch


def cancel_batch(db: Session, user_id: int, account_id: int, batch_id: int) -> None:
    batch = get_batch(db, user_id, account_id, batch_id)
    if batch.status != "pending":
        raise ValueError("Este lote já foi finalizado.")
    batch.status = "cancelled"
    db.commit()


def _match_candidates_for_line(
    db: Session,
    user_id: int,
    account_id: int,
    line: OfxImportLine,
) -> list[Transaction]:
    tx_type = _tx_type_for_direction(line.direction)  # type: ignore[arg-type]
    window_start = line.posted_date - timedelta(days=DATE_WINDOW_DAYS)
    window_end = line.posted_date + timedelta(days=DATE_WINDOW_DAYS)
    rows = list(
        db.scalars(
            select(Transaction).where(
                Transaction.user_id == user_id,
                Transaction.account_id == account_id,
                Transaction.card_id.is_(None),
                Transaction.type == tx_type,
                Transaction.amount_cents == line.amount_cents,
                Transaction.ofx_fitid.is_(None),
            )
        ).all()
    )
    out: list[Transaction] = []
    for tx in rows:
        dates = [tx.competence_date, tx.transaction_date, tx.due_date, tx.payment_date]
        if any(d is not None and window_start <= d <= window_end for d in dates):
            out.append(tx)
    out.sort(
        key=lambda tx: (
            0 if tx.status == "planned" else 1,
            -ofx_common.description_score(line.memo, tx.description),
            tx.id,
        )
    )
    return out


def line_review_payload(
    db: Session,
    user_id: int,
    account_id: int,
    line: OfxImportLine,
) -> dict[str, Any]:
    chosen = line.chosen_action or line.suggested_action
    tx_type = _tx_type_for_direction(line.direction)  # type: ignore[arg-type]
    payload: dict[str, Any] = {
        "id": line.id,
        "fitid": line.fitid,
        "posted_date": line.posted_date.isoformat(),
        "amount_cents": line.amount_cents,
        "amount": brl(line.amount_cents),
        "direction": line.direction,
        "memo": line.memo,
        "tx_type": tx_type,
        "suggested_action": line.suggested_action,
        "chosen_action": chosen,
        "chosen_transaction_id": line.chosen_transaction_id or line.suggested_transaction_id,
        "chosen_category_id": line.chosen_category_id or line.suggested_category_id,
        "candidates": [],
        "category_options": _categories_for_type(db, user_id, tx_type),
    }
    for tx in _match_candidates_for_line(db, user_id, account_id, line):
        payload["candidates"].append(
            {
                "id": tx.id,
                "description": tx.description,
                "status": tx.status,
                "competence_date": tx.competence_date.isoformat(),
                "score": round(ofx_common.description_score(line.memo, tx.description), 2),
            }
        )
    return payload


def batch_review_context(db: Session, batch: OfxImportBatch) -> dict[str, Any]:
    if batch.account_id is None:
        raise ValueError("Lote não é de conta bancária.")
    lines = [
        line_review_payload(db, batch.user_id, batch.account_id, line) for line in batch.lines
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
            "already_imported": sum(
                1 for ln in lines if ln["suggested_action"] == "already_imported"
            ),
            "skip": sum(1 for ln in lines if ln["suggested_action"] == "skip"),
        },
    }


def _parse_choice_action(raw: str | None, fallback: str | None) -> Action:
    allowed = {"create", "match", "skip", "already_imported"}
    value = (raw if raw is not None and str(raw).strip() != "" else (fallback or "")).strip()
    if not value:
        raise ValueError("Confirme a ação de cada lançamento.")
    if value not in allowed:
        raise ValueError(f"Ação inválida: {value}")
    return value  # type: ignore[return-value]


def apply_batch(
    db: Session,
    user_id: int,
    account: Account,
    batch_id: int,
    choices: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    from app.services import finance

    batch = get_batch(db, user_id, account.id, batch_id)
    if batch.status != "pending":
        raise ValueError("Este lote já foi finalizado.")

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
        "skipped": 0,
        "already_imported": 0,
    }

    for line in batch.lines:
        choice = choices.get(line.id, {})
        if line.suggested_action == "already_imported" and not choice.get("action"):
            action: Action = "already_imported"
        else:
            raw_action = choice.get("action")
            if raw_action is None or str(raw_action).strip() == "":
                action = _parse_choice_action(None, line.chosen_action or line.suggested_action)
            else:
                action = _parse_choice_action(str(raw_action), None)

        tx_id = choice.get("transaction_id")
        cat_id = choice.get("category_id")
        if tx_id is not None and tx_id != "":
            tx_id = int(tx_id)
        else:
            tx_id = line.chosen_transaction_id or line.suggested_transaction_id
        if cat_id is not None and cat_id != "":
            cat_id = int(cat_id)
        else:
            cat_id = line.chosen_category_id or line.suggested_category_id

        line.chosen_action = action
        line.chosen_transaction_id = tx_id if action == "match" else None
        line.chosen_category_id = cat_id if action in ("create", "match") else None

        if action in ("skip", "already_imported"):
            summary["skipped" if action == "skip" else "already_imported"] += 1
            continue

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

        tx_type = _tx_type_for_direction(line.direction)  # type: ignore[arg-type]
        resolved_cat = ofx_common._resolve_category(db, user_id, cat_id, memo=line.memo)

        if action == "create":
            finance.create_transaction(
                db,
                user_id,
                TransactionCreate(
                    account_id=account.id,
                    category_id=resolved_cat,
                    type=tx_type,  # type: ignore[arg-type]
                    amount_cents=line.amount_cents,
                    description=line.memo or ("Despesa OFX" if tx_type == "expense" else "Receita OFX"),
                    competence_date=line.posted_date,
                    due_date=line.posted_date,
                    payment_date=line.posted_date,
                    status="actual",
                    ofx_fitid=line.fitid,
                ),
            )
            if resolved_cat is not None:
                ofx_common.remember_category(db, user_id, line.memo, resolved_cat)
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
                or tx.account_id != account.id
                or tx.card_id is not None
                or tx.type != tx_type
                or tx.amount_cents != line.amount_cents
            ):
                raise ValueError("Lançamento inválido para conciliação.")
            if tx.ofx_fitid and tx.ofx_fitid != line.fitid:
                raise ValueError("Lançamento já conciliado com outro FITID.")

            if tx.status == "planned":
                if resolved_cat is not None:
                    tx.category_id = resolved_cat
                    db.flush()
                result = finance.realize_planned(
                    db,
                    user_id,
                    RealizePlannedInput(
                        planned_id=tx.id,
                        payment_date=line.posted_date,
                    ),
                )
                actual_id = result["actual"]["id"]
                actual = db.get(Transaction, actual_id)
                if actual is None:
                    raise ValueError("Falha ao realizar previsto na conciliação.")
                actual.ofx_fitid = line.fitid
                if resolved_cat is not None:
                    actual.category_id = resolved_cat
                    ofx_common.remember_category(db, user_id, line.memo, resolved_cat)
                db.commit()
            else:
                tx.ofx_fitid = line.fitid
                if resolved_cat is not None:
                    tx.category_id = resolved_cat
                    ofx_common.remember_category(db, user_id, line.memo, resolved_cat)
                db.commit()
            summary["matched"] += 1
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
    if summary.get("skipped"):
        parts.append(f"{summary['skipped']} ignorados")
    if summary.get("already_imported"):
        parts.append(f"{summary['already_imported']} já importados")
    if not parts:
        return "Importação OFX concluída sem alterações."
    return "Importação OFX: " + ", ".join(parts) + "."
