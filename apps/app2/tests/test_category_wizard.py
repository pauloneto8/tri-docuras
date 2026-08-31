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
