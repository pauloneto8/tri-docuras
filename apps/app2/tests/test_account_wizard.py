import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.auth import create_user
from app.models import Account, Category, Transaction, User
from app.schemas import CreateAccountInput, ListTransactionsInput
from app.services import finance
from app.services.account_wizard import (
    begin_account_wizard,
    detect_account_creation,
    looks_like_amount,
    process_wizard_message,
    try_process_account_wizard,
)
from app.services.intents import wants_account_creation
from app.services.tools import format_tool_result


def test_detect_account_creation_simple():
    assert detect_account_creation("cadastrar conta") is not None
    assert detect_account_creation("gastei 45 no mercado") is None


def test_detect_account_creation_with_details():
    data = detect_account_creation("cadastrar conta nubank corrente com 500")
    assert data is not None
    assert data.get("account_type") == "corrente"
    assert data.get("opening_balance") == "500"


def test_wizard_asks_for_name():
    session = {}
    result = begin_account_wizard(session, "cadastrar conta")
    assert "apelido" in result.message.lower()
    assert session.get("account_wizard") is not None


def test_detect_account_creation_with_uma():
    assert detect_account_creation("cadastrar uma conta do Nubank") is not None


def test_wizard_starts_for_cadastrar_uma_conta():
    session = {}
    result = begin_account_wizard(session, "cadastrar uma conta do Nubank")
    assert "apelido" in result.message.lower() or "tipo" in result.message.lower()
    assert session.get("account_wizard") is not None


def test_wizard_skips_known_fields():
    session = {}
    result = begin_account_wizard(session, "cadastrar conta nubank corrente")
    assert session["account_wizard"]["name"].lower() == "nubank"
    assert session["account_wizard"]["account_type"] == "corrente"
    assert session["account_wizard"]["institution"] == "Nubank"
    assert "saldo" in result.message.lower()


def test_bancaria_is_not_account_name():
    data = detect_account_creation("Cadastrar conta bancária do BN")
    assert data is not None
    assert data.get("name") == "Nubank"
    assert data.get("institution") == "Nubank"
    session = {}
    result = begin_account_wizard(session, "Cadastrar conta bancária do BN")
    assert session["account_wizard"]["name"] == "Nubank"
    assert "bancária" not in session["account_wizard"]["name"].lower()
    assert "tipo" in result.message.lower()


def test_extract_banco_do_brasil():
    data = detect_account_creation("cadastrar conta Banco do Brasil corrente")
    assert data is not None
    assert data.get("institution") == "Banco do Brasil"
    assert data.get("account_type") == "corrente"
    assert data.get("name") is None


def test_detect_adicione_conta_banco_do_brasil():
    assert wants_account_creation("Adicione a conta Banco do Brasil")
    data = detect_account_creation("Adicione a conta Banco do Brasil")
    assert data is not None
    assert data.get("institution") == "Banco do Brasil"
    assert data.get("name") is None
    session = {}
    result = begin_account_wizard(session, "Adicione a conta Banco do Brasil")
    assert "apelido" in result.message.lower()
    assert session["account_wizard"]["institution"] == "Banco do Brasil"
    assert result.source == "wizard"


def test_detect_imperative_forms():
    for phrase in (
        "Cadastre uma conta",
        "Crie conta nubank",
        "Registre a conta itau",
    ):
        assert wants_account_creation(phrase), phrase


def test_looks_like_amount():
    assert looks_like_amount("5,00 reais")
    assert looks_like_amount("R$ 5,00")
    assert not looks_like_amount("Nubank")


def test_nubank_com_saldo_usa_instituicao_como_apelido():
    phrase = "Adicione a conta bancária do Nubank com saldo de 5,00 reais"
    data = detect_account_creation(phrase)
    assert data is not None
    assert data.get("institution") == "Nubank"
    assert data.get("name") == "Nubank"
    assert data.get("opening_balance") is not None
    session = {}
    result = begin_account_wizard(session, phrase)
    assert session["account_wizard"]["name"] == "Nubank"
    assert "tipo" in result.message.lower()
    assert "5,00 reais" not in (session["account_wizard"].get("name") or "")


def test_wizard_restarts_on_new_account_intent():
    session = {}
    begin_account_wizard(session, "Adicione a conta bancária do Nubank com saldo de 5,00 reais")
    process_wizard_message(session, "corrente")
    assert session["account_wizard"]["name"] == "Nubank"

    restarted = try_process_account_wizard(
        session, "Cadastrar a conta bancária Nubank com saldo de 5 reais"
    )
    assert restarted is not None
    assert restarted.source == "wizard"
    assert session["account_wizard"]["name"] == "Nubank"
    assert session["account_wizard"]["opening_balance"] is not None


def test_wizard_rejects_money_as_nickname():
    session = {}
    begin_account_wizard(session, "cadastrar conta")
    result = process_wizard_message(session, "5,00 reais")
    assert result is None
    assert session.get("account_wizard") is None


def test_wizard_full_flow():
    session = {}
    begin_account_wizard(session, "cadastrar conta")
    r1 = process_wizard_message(session, "Itaú Poupança")
    assert r1 is not None
    assert "tipo" in r1.message.lower()
    r2 = process_wizard_message(session, "poupança")
    assert r2 is not None
    r3 = process_wizard_message(session, "Itaú")
    assert r3 is not None
    r4 = process_wizard_message(session, "1000")
    assert r4 is not None
    assert r4.needs_confirmation
    assert r4.pending_action["tool"] == "create_account"
    assert r4.pending_action["arguments"]["name"] == "Itaú Poupança"
    assert r4.pending_action["arguments"]["account_type"] == "poupanca"


def test_wizard_same_name_and_institution_does_not_reask_nickname():
    """Reproduz conversa real: apelido e instituição iguais não devem reabrir o passo do apelido."""
    session = {}
    begin_account_wizard(session, "Quero cadastrar uma nova conta")
    process_wizard_message(session, "Mercado Pago")
    process_wizard_message(session, "Conta corrente")
    process_wizard_message(session, "Mercado Pago")
    result = process_wizard_message(session, "889,63")
    assert result is not None
    assert result.needs_confirmation
    assert result.pending_action["arguments"]["name"] == "Mercado Pago"
    assert result.pending_action["arguments"]["institution"] == "Mercado Pago"
    assert result.pending_action["arguments"]["opening_balance"] in {"889.63", "889,63"}


def test_format_create_account():
    msg = format_tool_result(
        "create_account",
        {
            "name": "Nubank",
            "account_type_label": "Corrente",
            "institution": "Nubank",
            "opening_balance": "500.00",
        },
    )
    assert "Nubank" in msg
    assert "cadastrada" in msg


@pytest.fixture
def db_session():
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_create_account_isolation(db_session):
    suffix = uuid.uuid4().hex[:8]
    user_a = create_user(
        db_session,
        email=f"acct_a_{suffix}@example.com",
        password="secret1",
        name="User A",
        is_active=True,
    )
    user_b = create_user(
        db_session,
        email=f"acct_b_{suffix}@example.com",
        password="secret2",
        name="User B",
        is_active=True,
    )

    finance.create_account(
        db_session,
        user_a.id,
        CreateAccountInput(name=f"ContaA_{suffix}", account_type="corrente"),
    )

    accounts_a = db_session.scalars(
        select(Account).where(Account.user_id == user_a.id, Account.name == f"ContaA_{suffix}")
    ).all()
    accounts_b = db_session.scalars(
        select(Account).where(Account.user_id == user_b.id, Account.name == f"ContaA_{suffix}")
    ).all()

    assert len(accounts_a) == 1
    assert len(accounts_b) == 0

    db_session.query(Transaction).filter(Transaction.user_id.in_([user_a.id, user_b.id])).delete(
        synchronize_session=False
    )
    db_session.query(Account).filter(Account.user_id.in_([user_a.id, user_b.id])).delete(
        synchronize_session=False
    )
    db_session.query(User).filter(User.id.in_([user_a.id, user_b.id])).delete(
        synchronize_session=False
    )
    db_session.commit()
