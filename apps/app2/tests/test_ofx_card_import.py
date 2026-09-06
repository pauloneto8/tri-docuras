import uuid
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.auth import create_user
from app.config import settings
from app.models import Account, CardInvoice, Category, CreditCard, OfxImportBatch, Transaction, User
from app.schemas import CreateAccountInput, CreateCardInput, RegisterExpenseInput
from app.services import finance
from app.services.ofx_card_import import (
    apply_batch,
    create_batch,
    parse_ofx,
)


FIXTURE = Path(__file__).parent / "fixtures" / "card_sample.ofx"


def _setup_user(db, user):
    finance.seed_defaults(db, user.id)


def _create_debit(db, user_id, name, balance="10000"):
    return finance.create_account(
        db,
        user_id,
        CreateAccountInput(
            name=name,
            account_type="corrente",
            opening_balance=balance,
            opening_balance_date=date(2026, 1, 1),
        ),
    )


def _create_card(db, user_id, name, settlement_account_name, closing=10, due=17, limit="5000"):
    return finance.create_card(
        db,
        user_id,
        CreateCardInput(
            name=name,
            institution="Nubank",
            closing_day=closing,
            due_day=due,
            credit_limit=limit,
            settlement_account_name=settlement_account_name,
        ),
    )


def _cleanup(db, user_id):
    db.query(OfxImportBatch).filter(OfxImportBatch.user_id == user_id).delete(
        synchronize_session=False
    )
    db.query(Transaction).filter(Transaction.user_id == user_id).delete(
        synchronize_session=False
    )
    from app.models import InstallmentPlan

    db.query(InstallmentPlan).filter(InstallmentPlan.user_id == user_id).delete(
        synchronize_session=False
    )
    db.query(CardInvoice).filter(CardInvoice.user_id == user_id).delete(
        synchronize_session=False
    )
    db.query(CreditCard).filter(CreditCard.user_id == user_id).delete(
        synchronize_session=False
    )
    db.query(Account).filter(Account.user_id == user_id).delete(synchronize_session=False)
    db.query(Category).filter(Category.user_id == user_id).delete(synchronize_session=False)
    db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
    db.commit()


def test_parse_ofx_sample():
    txns = parse_ofx(FIXTURE.read_text(encoding="utf-8"))
    assert len(txns) == 3
    assert txns[0].direction == "debit"
    assert txns[0].amount_cents == 15000
    assert txns[0].fitid == "FIT-MERCADO-001"
    assert txns[0].posted_date == date(2026, 8, 5)
    assert txns[2].direction == "credit"
    assert txns[2].amount_cents == 23990


def test_ofx_create_and_match_and_idempotent():
    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"ofx_{suffix}@test.com",
        password="secret1",
        name="OFX User",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        debit = _create_debit(db, user.id, f"Corrente_{suffix}")
        card_data = _create_card(db, user.id, f"Nubank_{suffix}", debit["name"])
        card = finance.find_card(db, user.id, card_id=card_data["id"])
        assert card is not None
        cat = db.scalar(
            select(Category).where(Category.user_id == user.id, Category.type == "expense")
        )
        # Existing purchase to match first OFX debit
        finance.register_expense(
            db,
            user.id,
            RegisterExpenseInput(
                amount="150",
                description="Mercado Extra",
                card_name=card.name,
                category_name=cat.name,
                competence_date=date(2026, 8, 5),
                status="planned",
            ),
        )

        content = FIXTURE.read_bytes()
        batch = create_batch(db, user.id, card, "card_sample.ofx", content)
        assert batch.status == "pending"
        assert len(batch.lines) == 3

        by_fitid = {ln.fitid: ln for ln in batch.lines}
        assert by_fitid["FIT-MERCADO-001"].suggested_action == "match"
        assert by_fitid["FIT-UBER-002"].suggested_action == "create"
        # Credit without matching invoice total -> skip
        assert by_fitid["FIT-PAGTO-003"].suggested_action == "skip"

        choices = {
            ln.id: {
                "action": ln.suggested_action,
                "transaction_id": ln.suggested_transaction_id,
                "invoice_id": ln.suggested_invoice_id,
            }
            for ln in batch.lines
        }
        summary = apply_batch(db, user.id, card, batch.id, choices)
        assert summary["matched"] == 1
        assert summary["created"] == 1
        assert summary["skipped"] == 1

        matched = db.scalar(
            select(Transaction).where(
                Transaction.user_id == user.id,
                Transaction.ofx_fitid == "FIT-MERCADO-001",
            )
        )
        created = db.scalar(
            select(Transaction).where(
                Transaction.user_id == user.id,
                Transaction.ofx_fitid == "FIT-UBER-002",
            )
        )
        assert matched is not None
        assert created is not None
        assert created.status == "planned"
        assert created.card_id == card.id
        assert created.invoice_id is not None

        # Reimport: FITIDs aplicados → already_imported; crédito só ignorado continua skip
        batch2 = create_batch(db, user.id, card, "card_sample.ofx", content)
        by2 = {ln.fitid: ln.suggested_action for ln in batch2.lines}
        assert by2["FIT-MERCADO-001"] == "already_imported"
        assert by2["FIT-UBER-002"] == "already_imported"
        assert by2["FIT-PAGTO-003"] == "skip"
        choices2 = {
            ln.id: {"action": ln.suggested_action} for ln in batch2.lines
        }
        summary2 = apply_batch(db, user.id, card, batch2.id, choices2)
        assert summary2["already_imported"] == 2
        assert summary2["skipped"] == 1
    finally:
        _cleanup(db, user.id)
        db.close()


def test_ofx_pay_invoice_from_credit():
    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"ofxpay_{suffix}@test.com",
        password="secret1",
        name="OFX Pay",
        is_active=True,
    )
    try:
        _setup_user(db, user)
        debit = _create_debit(db, user.id, f"Corrente_{suffix}")
        card_data = _create_card(db, user.id, f"Visa_{suffix}", debit["name"])
        card = finance.find_card(db, user.id, card_id=card_data["id"])
        assert card is not None
        cat = db.scalar(
            select(Category).where(Category.user_id == user.id, Category.type == "expense")
        )
        finance.register_expense(
            db,
            user.id,
            RegisterExpenseInput(
                amount="239,90",
                description="Compras do mês",
                card_name=card.name,
                category_name=cat.name,
                competence_date=date(2026, 8, 8),
                status="planned",
            ),
        )
        ofx = """
<OFX>
<CREDITCARDMSGSRSV1>
<CCSTMTTRNRS>
<CCSTMTRS>
<BANKTRANLIST>
<STMTTRN>
<TRNTYPE>CREDIT
<DTPOSTED>20260820
<TRNAMT>239.90
<FITID>FIT-PAG-ONLY-1
<MEMO>PAGAMENTO FATURA
</STMTTRN>
</BANKTRANLIST>
</CCSTMTRS>
</CCSTMTTRNRS>
</CREDITCARDMSGSRSV1>
</OFX>
"""
        batch = create_batch(db, user.id, card, "pay.ofx", ofx)
        assert len(batch.lines) == 1
        line = batch.lines[0]
        assert line.suggested_action == "pay_invoice"
        assert line.suggested_invoice_id is not None

        summary = apply_batch(
            db,
            user.id,
            card,
            batch.id,
            {
                line.id: {
                    "action": "pay_invoice",
                    "invoice_id": line.suggested_invoice_id,
                }
            },
        )
        assert summary["payments"] == 1
        inv = db.get(CardInvoice, line.suggested_invoice_id)
        assert inv is not None
        assert inv.status == "paid"
        pay_tx = db.scalar(
            select(Transaction).where(
                Transaction.user_id == user.id,
                Transaction.ofx_fitid == "FIT-PAG-ONLY-1",
            )
        )
        assert pay_tx is not None
        assert pay_tx.card_id is None
        assert pay_tx.type == "expense"
    finally:
        _cleanup(db, user.id)
        db.close()
