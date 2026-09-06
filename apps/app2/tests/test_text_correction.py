from app.services.text_correction import (
    correct_category_name,
    correct_movement_description,
    sanitize_movement_description,
)
from app.services.tools import extract_description, parse_amount


def test_sanitize_strips_command_and_account():
    assert (
        sanitize_movement_description("Comprando carne no mercado na carteira")
        == "compra de carne no mercado"
    )
    assert (
        correct_movement_description("Comprando carne no mercado na carteira")
        == "Compra de carne no mercado"
    )


def test_extract_description_keeps_compra_de():
    msg = "fiz compra de carne no mercado na carteira"
    assert extract_description(msg, parse_amount(msg)).lower() == "compra de carne no mercado"


def test_extract_description_with_amount_and_account():
    msg = "gastei 40 na compra de carne no mercado na carteira"
    assert "compra de carne" in extract_description(msg, parse_amount(msg)).lower()
    assert "carteira" not in extract_description(msg, parse_amount(msg)).lower()


def test_corrects_missing_accents():
    assert correct_movement_description("alimentacao no mercado") == "Alimentação no mercado"


def test_corrects_city_name():
    assert (
        correct_movement_description("passagens para cidade de Timbauba")
        == "Passagens para cidade de Timbaúba"
    )


def test_preserves_already_correct_text():
    text = "Passagens para cidade de Timbaúba"
    assert correct_movement_description(text) == text


def test_preserves_english_words_in_description():
    assert correct_movement_description("mercado user A") == "Mercado user A"


def test_corrects_salary_word():
    assert correct_movement_description("salario mensal") == "Salário mensal"


def test_correct_category_name_lowercase():
    assert correct_category_name("consumo") == "Consumo"
    assert correct_category_name("assinaturas") == "Assinaturas"
    assert correct_category_name("alimentacao") == "Alimentação"


def test_correct_category_name_preserves_proper_case():
    assert correct_category_name("Pet") == "Pet"
    assert correct_category_name("Freelance") == "Freelance"
