"""Testes da importação OFX/CSV de contas bancárias."""

import uuid
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.auth import create_user
from app.config import settings
from app.models import Transaction
from app.schemas import CreateAccountInput, RegisterExpenseInput
from app.services import finance
from app.services.ofx_account_import import apply_batch, create_batch
from app.services.statement_parse import parse_csv, parse_statement


FIXTURE_OFX = Path(__file__).parent / "fixtures" / "bank_sample.ofx"
FIXTURE_CSV = Path(__file__).parent / "fixtures" / "bank_sample.csv"


def _engine():
    return create_engine(settings.database_url)


def _unique_email():
    return f"bank_ofx_{uuid.uuid4().hex[:10]}@test.com"


def _user(db):
    return create_user(
        db,
        email=_unique_email(),
        password="senha123",
        name="Bank OFX",
        is_active=True,
    )


def test_parse_bank_ofx_fixture():
    txns = parse_statement(FIXTURE_OFX.read_bytes(), filename="bank_sample.ofx")
    assert len(txns) == 3
    debits = [t for t in txns if t.direction == "debit"]
    credits = [t for t in txns if t.direction == "credit"]
    assert len(debits) == 2
    assert len(credits) == 1
    assert credits[0].amount_cents == 350_000


def test_parse_bank_csv_fixture():
    txns = parse_csv(FIXTURE_CSV.read_bytes())
    assert len(txns) == 3
    assert txns[0].direction == "debit"
    assert txns[0].amount_cents == 7550
    assert txns[1].direction == "credit"
    assert txns[1].fitid == "CSV-SALARIO-002"
    via_statement = parse_statement(FIXTURE_CSV.read_bytes(), filename="extrato.csv")
    assert len(via_statement) == 3


def test_create_and_apply_bank_ofx_creates_actuals():
    Session = sessionmaker(bind=_engine())
    db = Session()
    try:
        user = _user(db)
        finance.seed_defaults(db, user.id)
        account_data = finance.create_account(
            db,
            user.id,
            CreateAccountInput(
                name=f"Corrente {uuid.uuid4().hex[:6]}",
                account_type="corrente",
                opening_balance="1000",
                opening_balance_date=date(2026, 1, 1),
            ),
        )
        account = finance.find_account(db, user.id, account_id=account_data["id"])
        assert account is not None
        batch = create_batch(
            db, user.id, account, "bank_sample.ofx", FIXTURE_OFX.read_bytes()
        )
        assert batch.account_id == account.id
        assert batch.card_id is None
        assert batch.status == "pending"
        assert len(batch.lines) == 3

        choices = {
            line.id: {
                "action": line.suggested_action,
                "category_id": line.suggested_category_id or "",
            }
            for line in batch.lines
        }
        summary = apply_batch(db, user.id, account, batch.id, choices)
        assert summary["created"] == 3

        txs = list(
            db.scalars(
                select(Transaction).where(
                    Transaction.user_id == user.id,
                    Transaction.account_id == account.id,
                    Transaction.ofx_fitid.is_not(None),
                )
            ).all()
        )
        assert len(txs) == 3
        assert all(t.status == "actual" for t in txs)
        assert all(t.card_id is None for t in txs)
        incomes = [t for t in txs if t.type == "income"]
        expenses = [t for t in txs if t.type == "expense"]
        assert len(incomes) == 1
        assert len(expenses) == 2

        batch2 = create_batch(
            db, user.id, account, "bank_sample.ofx", FIXTURE_OFX.read_bytes()
        )
        assert all(ln.suggested_action == "already_imported" for ln in batch2.lines)
    finally:
        db.close()


def test_create_and_apply_bank_csv():
    Session = sessionmaker(bind=_engine())
    db = Session()
    try:
        user = _user(db)
        finance.seed_defaults(db, user.id)
        account_data = finance.create_account(
            db,
            user.id,
            CreateAccountInput(
                name=f"CSV Acc {uuid.uuid4().hex[:6]}",
                account_type="corrente",
                opening_balance="2000",
                opening_balance_date=date(2026, 1, 1),
            ),
        )
        account = finance.find_account(db, user.id, account_id=account_data["id"])
        assert account is not None
        batch = create_batch(
            db, user.id, account, "bank_sample.csv", FIXTURE_CSV.read_bytes()
        )
        assert len(batch.lines) == 3
        choices = {
            line.id: {"action": "create", "category_id": line.suggested_category_id or ""}
            for line in batch.lines
        }
        summary = apply_batch(db, user.id, account, batch.id, choices)
        assert summary["created"] == 3
        fitids = set(
            db.scalars(
                select(Transaction.ofx_fitid).where(
                    Transaction.user_id == user.id,
                    Transaction.account_id == account.id,
                )
            ).all()
        )
        assert "CSV-MERCADO-001" in fitids
        assert "CSV-SALARIO-002" in fitids
    finally:
        db.close()


def test_bank_ofx_match_existing_actual():
    Session = sessionmaker(bind=_engine())
    db = Session()
    try:
        user = _user(db)
        finance.seed_defaults(db, user.id)
        account_data = finance.create_account(
            db,
            user.id,
            CreateAccountInput(
                name=f"Poupança {uuid.uuid4().hex[:6]}",
                account_type="poupanca",
                opening_balance="500",
                opening_balance_date=date(2026, 1, 1),
            ),
        )
        account = finance.find_account(db, user.id, account_id=account_data["id"])
        assert account is not None
        finance.register_expense(
            db,
            user.id,
            RegisterExpenseInput(
                amount="75,50",
                description="MERCADO EXTRA",
                account_name=account.name,
                category_name="Alimentação",
                payment_date=date(2026, 8, 5),
            ),
        )
        batch = create_batch(
            db, user.id, account, "bank_sample.ofx", FIXTURE_OFX.read_bytes()
        )
        mercado = next(ln for ln in batch.lines if "MERCADO" in ln.memo.upper())
        assert mercado.suggested_action == "match"
        assert mercado.suggested_transaction_id is not None

        choices = {}
        for line in batch.lines:
            if line.id == mercado.id:
                choices[line.id] = {
                    "action": "match",
                    "transaction_id": line.suggested_transaction_id,
                    "category_id": line.suggested_category_id or "",
                }
            else:
                choices[line.id] = {"action": "skip"}
        summary = apply_batch(db, user.id, account, batch.id, choices)
        assert summary["matched"] == 1
        assert summary["skipped"] == 2

        tx = db.get(Transaction, mercado.suggested_transaction_id)
        assert tx is not None
        assert tx.ofx_fitid == mercado.fitid
    finally:
        db.close()
