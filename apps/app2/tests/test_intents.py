from app.services.intents import (
    wants_account_creation,
    wants_category_creation,
    wants_list_accounts,
    wants_list_categories,
    wants_register_expense,
    wants_register_income,
)


def test_wants_list_accounts_from_conversations():
    assert wants_list_accounts("Quais a conta bancária?")
    assert wants_list_accounts("Liste minhas contas bancárias")
    assert wants_list_accounts("Quero ver quais são as contas bancária")
    assert wants_list_accounts("minhas contas")


def test_wants_list_accounts_not_creation():
    assert not wants_list_accounts("Cadastrar uma nova conta bancária")
    assert not wants_list_accounts("cadastrar conta nubank")
    assert not wants_list_accounts("Cadastro da conta bancária do Mercado Pago")
    assert not wants_list_accounts("Realize o cadastro da conta bancária do Mercado Pago")


def test_wants_account_creation_not_list():
    assert wants_account_creation("Cadastrar a conta bancária")
    assert wants_account_creation("Cadastrar uma nova conta bancária")
    assert wants_account_creation("Cadastro da conta bancária do Mercado Pago")
    assert wants_account_creation("Realize o cadastro da conta bancária do Mercado Pago")
    assert wants_account_creation("cadastro de conta Mercado Pago")
    assert not wants_account_creation("Quais a conta bancária?")
    assert not wants_account_creation("Liste minhas contas")


def test_rule_create_account_from_cadastro_noun():
    from app.services.tools import try_rule_based_parse

    tool = try_rule_based_parse("Cadastro da conta bancária do Mercado Pago")
    assert tool is not None
    assert tool.tool == "create_account"
    assert tool.arguments.get("institution") == "Mercado Pago"

def test_wants_list_categories_from_conversations():
    assert wants_list_categories("Quais são as categorias?")
    assert wants_list_categories("Liste minhas categorias")
    assert wants_list_categories("Quero ver quais categorias tenho")
    assert wants_list_categories("minhas categorias")


def test_wants_list_categories_not_creation():
    assert not wants_list_categories("Cadastrar uma nova categoria")
    assert not wants_list_categories("cadastrar categoria Pet")


def test_wants_category_creation_not_list():
    assert wants_category_creation("Cadastrar uma nova categoria")
    assert wants_category_creation("Criar categoria Pet")
    assert not wants_category_creation("Quais são as categorias?")
    assert not wants_category_creation("Liste minhas categorias")


def test_wants_register_expense_from_conversations():
    assert wants_register_expense("Despesa")
    assert wants_register_expense("Lance uma despesa")
    assert wants_register_expense("Quero lançar uma despesa")
    assert wants_register_expense("Registrar despesa")
    assert wants_register_expense("Lance 7,66 de compras na Shopee")
    assert wants_register_expense("Lance 7,66 referente a compra na Shopee")
    assert wants_register_expense(
        "17,54 do presente de amigo secreto no cartão do mercado pago"
    )
    assert wants_register_expense(
        "Hoje tive o custo de 27 na compra de frutas na conta da carteira"
    )
    assert wants_register_expense(
        "Hoje tive o curso de 27 na compra de frutas na conta da carteira"
    )


def test_rule_expense_from_conversation_failures():
    from app.services.tools import try_rule_based_parse

    tool = try_rule_based_parse("Lance 7,66 referente a compra na Shopee")
    assert tool is not None
    assert tool.tool == "register_expense"
    assert tool.arguments.get("amount") == "7.66"
    assert "shopee" in tool.arguments.get("description", "").lower()

    tool = try_rule_based_parse(
        "17,54 do presente de amigo secreto no cartão do mercado pago"
    )
    assert tool is not None
    assert tool.tool == "register_expense"
    assert "presente" in tool.arguments.get("description", "").lower()
    assert "cartão" not in tool.arguments.get("description", "").lower()
    assert "cartao" not in tool.arguments.get("description", "").lower()


def test_extract_description_farmacia_strips_article():
    from app.services.tools import extract_description, parse_amount

    msg = "Gastei 32,24 com a farmácia do Trabalhador"
    desc = extract_description(msg, parse_amount(msg))
    assert desc.lower().startswith("farmácia") or desc.lower().startswith("farmacia")
    assert not desc.lower().startswith("a ")


def test_flash_account_defaults_institution_to_name():
    from app.services.account_wizard import begin_account_wizard

    session = {}
    begin_account_wizard(session, "cadastre a conta bancária Flash com saldo de 1,36")
    wizard = session["account_wizard"]
    assert wizard["name"] == "Flash"
    assert wizard["institution"] == "Flash"
    assert wizard["institution_asked"] is True


def test_wants_register_expense_not_list_or_summary():
    assert not wants_register_expense("Liste minhas despesas")
    assert not wants_register_expense("Quero ver minhas despesas")
    assert not wants_register_expense("Quanto gastei este mês")
    assert not wants_register_expense("Cadastrar uma nova categoria de despesa")


def test_wants_register_income_from_conversations():
    assert wants_register_income("Receita")
    assert wants_register_income("Lance uma receita")
    assert wants_register_income("Quero lançar uma receita")
    assert wants_register_income("Tive uma entrada de 550 referente a vale refeição")
    assert wants_register_income("entrada de 550")
    assert wants_register_income("recebi 1500 de salario")
    assert wants_register_income("Isso é uma receita")
    assert not wants_register_expense("Tive uma entrada de 550 referente a vale refeição")
    assert not wants_register_expense("entrada de 550")
    # Despesas com "tive" + contexto de gasto continuam despesa
    assert wants_register_expense(
        "Hoje tive o custo de 27 na compra de frutas na conta da carteira"
    )
    assert wants_register_expense(
        "Ontem tive as despesas de 54 de passagens para o trabalho"
    )


def test_resolve_intent_entrada_is_income():
    import asyncio

    from app.agent.runner import _resolve_intent

    async def _run():
        tool, source = await _resolve_intent(
            "Tive uma entrada de 550 referente a vale refeição"
        )
        assert tool is not None
        assert tool.tool == "register_income"
        assert tool.arguments.get("amount") == "550"
        assert source == "rule"

    asyncio.run(_run())
