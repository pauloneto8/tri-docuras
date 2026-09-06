import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.auth import create_user
from app.models import Category, User
from app.schemas import CreateCategoryInput
from app.services import finance
from app.services.category_wizard import (
    begin_category_wizard,
    process_wizard_message,
)
from app.services.intents import detect_category_creation, wants_category_creation
from app.services.tools import format_tool_result, try_rule_based_parse


def test_wants_category_creation():
    assert wants_category_creation("cadastrar categoria Pet")
    assert not wants_category_creation("gastei 45 no mercado")


def test_detect_category_creation_with_name_and_type():
    data = detect_category_creation("criar categoria de despesa Assinaturas")
    assert data is not None
    assert data.get("name") == "Assinaturas"
    assert data.get("type") == "expense"


def test_detect_multiple_categories():
    data = detect_category_creation(
        "Cadastre as categorias: Presente, Restaurante e Lazer."
    )
    assert data is not None
    assert data.get("names") == ["Presente", "Restaurante", "Lazer"]
    assert "name" not in data or data.get("name") is None


def test_rule_based_create_multiple_categories():
    result = try_rule_based_parse(
        "Cadastre as categorias: Presente, Restaurante e Lazer."
    )
    assert result is not None
    assert result.tool == "create_category"
    assert result.arguments["names"] == ["Presente", "Restaurante", "Lazer"]
    assert result.arguments["type"] == "expense"


def test_wizard_multiple_categories_confirmation():
    session = {}
    result = begin_category_wizard(
        session,
        "Cadastre as categorias: Presente, Restaurante e Lazer.",
        initial={"type": "expense"},
    )
    assert result.needs_confirmation is True
    assert result.pending_action["arguments"]["names"] == [
        "Presente",
        "Restaurante",
        "Lazer",
    ]
    assert "3 categorias" in result.message.lower() or "presente" in result.message.lower()


def test_single_category_with_e_keeps_one_name():
    data = detect_category_creation("Cadastre a categoria Vale e Auxílio")
    assert data is not None
    assert data.get("name") == "Vale e Auxílio"
    assert "names" not in data


def test_rule_based_create_category():
    result = try_rule_based_parse("cadastrar categoria Freelance de receita")
    assert result is not None
    assert result.tool == "create_category"
    assert result.arguments["name"] == "Freelance"
    assert result.arguments["type"] == "income"


def test_wizard_asks_for_name():
    session = {}
    result = begin_category_wizard(session, "cadastrar categoria")
    assert "nome" in result.message.lower()
    assert session.get("category_wizard") is not None


def test_wizard_confirmation():
    session = {}
    begin_category_wizard(session, "cadastrar categoria")
    process_wizard_message(session, "Assinaturas")
    result = process_wizard_message(session, "despesa")
    assert result is not None
    assert result.needs_confirmation is True
    assert result.pending_action["tool"] == "create_category"
    assert result.pending_action["arguments"]["name"] == "Assinaturas"
    assert result.pending_action["arguments"]["type"] == "expense"


def test_wizard_normalizes_category_name():
    session = {}
    begin_category_wizard(session, "cadastrar categoria")
    process_wizard_message(session, "consumo")
    result = process_wizard_message(session, "despesa")
    assert result is not None
    assert result.pending_action["arguments"]["name"] == "Consumo"


def test_wizard_asks_type_when_assumed_from_rules():
    session = {}
    result = begin_category_wizard(
        session,
        "Cadastre a categoria Vale e Auxílio",
        initial={"name": "Vale e Auxílio", "type": "expense", "_type_assumed": True},
    )
    assert result.needs_confirmation is not True
    assert "despesa" in result.message.lower() or "receita" in result.message.lower()
    assert session["category_wizard"]["name"] == "Vale e Auxílio"
    assert session["category_wizard"]["category_type"] is None


def test_wizard_keeps_explicit_income_type():
    session = {}
    result = begin_category_wizard(
        session,
        "Cadastrar a categoria de receita chamada Vale e Auxílio",
        initial={"name": "Vale e Auxílio", "type": "income"},
    )
    assert result.needs_confirmation is True
    assert result.pending_action["arguments"]["type"] == "income"
    assert result.pending_action["arguments"]["name"] == "Vale e Auxílio"


def test_create_category_via_finance():
    from app.config import settings

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"cat_{suffix}@test.com",
        password="secret1",
        name="Cat User",
        is_active=True,
    )
    try:
        finance.seed_defaults(db, user.id)
        result = finance.create_category(
            db,
            user.id,
            CreateCategoryInput(
                name=f"consumo_{suffix}",
                type="expense",
                keywords="veterinario,racao",
            ),
        )
        assert result["name"] == f"Consumo_{suffix}"
        assert result["type"] == "expense"
        msg = format_tool_result("create_category", result)
        assert f"Consumo_{suffix}" in msg
        assert "cadastrada" in msg

        # Mesmo nome, outro tipo → atualiza o tipo (nome é único por usuário)
        updated = finance.create_category(
            db,
            user.id,
            CreateCategoryInput(name=f"consumo_{suffix}", type="income"),
        )
        assert updated["type"] == "income"
        assert updated.get("updated") is True
        assert updated.get("previous_type") == "expense"
        msg2 = format_tool_result("create_category", updated)
        assert "atualizada" in msg2.lower()
        assert "receita" in msg2.lower()

        with pytest.raises(ValueError, match="Já existe"):
            finance.create_category(
                db,
                user.id,
                CreateCategoryInput(name=f"consumo_{suffix}", type="income"),
            )
    finally:
        db.query(Category).filter(Category.user_id == user.id).delete()
        db.query(User).filter(User.id == user.id).delete()
        db.commit()
        db.close()


def test_execute_batch_create_categories_skips_existing():
    from app.config import settings
    from app.schemas import ToolCall
    from app.services.tools import execute_tool

    engine = create_engine(settings.database_url)
    db = sessionmaker(bind=engine)()
    suffix = uuid.uuid4().hex[:8]
    user = create_user(
        db,
        email=f"cat_batch_{suffix}@test.com",
        password="secret1",
        name="Cat Batch",
        is_active=True,
    )
    try:
        finance.seed_defaults(db, user.id)
        # Lazer já existe nos defaults
        outcome = execute_tool(
            db,
            user.id,
            ToolCall(
                tool="create_category",
                arguments={
                    "names": [f"Presente_{suffix}", "Lazer", f"Restaurante_{suffix}"],
                    "type": "expense",
                },
            ),
        )
        result = outcome["result"]
        assert result["batch"] is True
        created_names = {c["name"] for c in result["created"]}
        assert f"Presente_{suffix}" in created_names
        assert f"Restaurante_{suffix}" in created_names
        assert "Lazer" in result["skipped"]
        msg = format_tool_result("create_category", result)
        assert "cadastrada" in msg.lower()
        assert "lazer" in msg.lower()
    finally:
        db.query(Category).filter(Category.user_id == user.id).delete()
        db.query(User).filter(User.id == user.id).delete()
        db.commit()
        db.close()
