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


def test_wants_account_creation_not_list():
    assert wants_account_creation("Cadastrar a conta bancária")
    assert wants_account_creation("Cadastrar uma nova conta bancária")
    assert not wants_account_creation("Quais a conta bancária?")
    assert not wants_account_creation("Liste minhas contas")


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


def test_wants_register_expense_not_list_or_summary():
    assert not wants_register_expense("Liste minhas despesas")
    assert not wants_register_expense("Quero ver minhas despesas")
    assert not wants_register_expense("Quanto gastei este mês")
    assert not wants_register_expense("Cadastrar uma nova categoria de despesa")


def test_wants_register_income_from_conversations():
    assert wants_register_income("Receita")
    assert wants_register_income("Lance uma receita")
    assert wants_register_income("Quero lançar uma receita")
