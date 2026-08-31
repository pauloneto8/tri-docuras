import uuid
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import create_user
from app.config import settings
from app.models import Account, Category, Transaction, User
from app.schemas import (
    CreateAccountInput,
    RegisterTransferInput,
    SummaryInput,
)
from app.services import finance
from app.services.intents import wants_transfer
from app.services.tools import try_rule_based_parse


def _cleanup(db, user):
    db.query(Transaction).filter(Transaction.user_id == user.id).delete(
        synchronize_session=False
    )
    db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
    db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
    db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
    db.commit()
    db.close()


def _create_two_accounts(db, user_id, suffix):
    finance.seed_defaults(db, user_id)
    a = finance.create_account(
        db,
        user_id,
        CreateAccountInput(name=f"Nubank_{suffix}", account_type="corrente", opening_balance="1000"),
    )
    b = finance.create_account(
        db,
        user_id,
        CreateAccountInput(name=f"Carteira_{suffix}", account_type="carteira", opening_balance="0"),
    )
    return a, b


def test_register_transfer_creates_pair():
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    db = Session()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"xfer_{suffix}@test.com",
        password="pass",
        name="Xfer User",
        is_active=True,
    )
    try:
        a, b = _create_two_accounts(db, user.id, suffix)
        result = finance.register_transfer(
            db,
            user.id,
            RegisterTransferInput(
                amount="100",
                from_account_name=a["name"],
                to_account_name=b["name"],
                transaction_date=date.today(),
            ),
        )
        assert result["from_account"] == a["name"]
        assert result["to_account"] == b["name"]
        assert result["amount"] == "100,00"

        txs = db.query(Transaction).filter(Transaction.user_id == user.id).all()
        transfer_txs = [t for t in txs if t.transfer_group_id]
        assert len(transfer_txs) == 2
        assert transfer_txs[0].transfer_group_id == transfer_txs[1].transfer_group_id
        types = {t.type for t in transfer_txs}
        assert types == {"transfer_out", "transfer_in"}

        balances = {item["account"]: item["balance_cents"] for item in finance.account_balances(db, user.id)}
        assert balances[a["name"]] == 100000 - 10000
        assert balances[b["name"]] == 10000
    finally:
        _cleanup(db, user)


def test_register_transfer_same_account_rejected():
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    db = Session()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"xfer2_{suffix}@test.com",
        password="pass",
        name="Xfer User",
        is_active=True,
    )
    try:
        a, _ = _create_two_accounts(db, user.id, suffix)
        try:
            finance.register_transfer(
                db,
                user.id,
                RegisterTransferInput(
                    amount="50",
                    from_account_name=a["name"],
                    to_account_name=a["name"],
                ),
            )
            assert False, "should raise"
        except ValueError as exc:
            assert "diferentes" in str(exc).lower()
    finally:
        _cleanup(db, user)


def test_summary_excludes_transfers_by_default():
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    db = Session()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"xfer3_{suffix}@test.com",
        password="pass",
        name="Xfer User",
        is_active=True,
    )
    try:
        a, b = _create_two_accounts(db, user.id, suffix)
        finance.register_transfer(
            db,
            user.id,
            RegisterTransferInput(
                amount="100",
                from_account_name=a["name"],
                to_account_name=b["name"],
                transaction_date=date.today(),
            ),
        )
        summary = finance.get_summary(db, user.id, SummaryInput(ref_date=date.today()))
        assert summary["income_cents"] == 0
        assert summary["expense_cents"] == 0
        assert summary["balance_cents"] == 0
        assert summary["ending_balance_cents"] == 100000
    finally:
        _cleanup(db, user)


def test_transfers_never_count_as_income_or_expense():
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    db = Session()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"xfer4_{suffix}@test.com",
        password="pass",
        name="Xfer User",
        is_active=True,
    )
    try:
        a, b = _create_two_accounts(db, user.id, suffix)
        finance.register_transfer(
            db,
            user.id,
            RegisterTransferInput(
                amount="100",
                from_account_name=a["name"],
                to_account_name=b["name"],
                transaction_date=date.today(),
            ),
        )
        summary = finance.get_summary(db, user.id, SummaryInput(ref_date=date.today()))
        assert summary["income_cents"] == 0
        assert summary["expense_cents"] == 0
        assert summary["balance_cents"] == 0
        assert summary["ending_balance_cents"] == 100000
    finally:
        _cleanup(db, user)


def test_rule_based_transfer_intent():
    tool = try_rule_based_parse("transferir 100 da Nubank para Carteira")
    assert tool is not None
    assert tool.tool == "register_transfer"
    assert tool.arguments["amount"] == "100"


def test_wants_transfer():
    assert wants_transfer("transferir 50 da nubank para carteira")
    assert not wants_transfer("gastei 50 no mercado")
