"""Testes do parser OFX/CSV compartilhado."""

from datetime import date
from pathlib import Path

from app.services.statement_parse import (
    detect_statement_format,
    parse_csv,
    parse_ofx,
    parse_statement,
)


BANK_OFX = Path(__file__).parent / "fixtures" / "bank_sample.ofx"
BANK_CSV = Path(__file__).parent / "fixtures" / "bank_sample.csv"
CARD_OFX = Path(__file__).parent / "fixtures" / "card_sample.ofx"


def test_detect_format_by_extension():
    assert detect_statement_format("x.csv", b"data,valor,descricao\n") == "csv"
    assert detect_statement_format("x.ofx", b"<OFX>") == "ofx"


def test_parse_csv_semicolon_br():
    txns = parse_csv(BANK_CSV.read_bytes())
    assert [(t.posted_date, t.direction, t.amount_cents) for t in txns] == [
        (date(2026, 8, 5), "debit", 7550),
        (date(2026, 8, 10), "credit", 350_000),
        (date(2026, 8, 15), "debit", 12_000),
    ]


def test_parse_csv_without_id_is_stable():
    raw = "data,valor,descricao\n2026-08-01,-10.00,Cafe\n"
    a = parse_csv(raw)
    b = parse_csv(raw)
    assert a[0].fitid == b[0].fitid
    assert a[0].fitid.startswith("CSV-")


def test_parse_csv_separate_debit_credit_columns():
    raw = (
        "data;descricao;debito;credito\n"
        "01/09/2026;Compra;50,00;\n"
        "02/09/2026;Deposito;;100,00\n"
    )
    txns = parse_csv(raw)
    assert txns[0].direction == "debit" and txns[0].amount_cents == 5000
    assert txns[1].direction == "credit" and txns[1].amount_cents == 10_000


def test_parse_csv_unknown_headers_inferred():
    raw = (
        "ColA;ColB;ColC\n"
        "05/08/2026;Padaria Central;-45,90\n"
        "06/08/2026;PIX Recebido;200,00\n"
    )
    txns = parse_csv(raw)
    assert len(txns) == 2
    assert txns[0].memo == "Padaria Central"
    assert txns[0].direction == "debit"
    assert txns[0].amount_cents == 4590
    assert txns[1].direction == "credit"
    assert txns[1].amount_cents == 20_000


def test_parse_csv_without_header_row():
    raw = (
        "05/08/2026;MERCADO EXTRA;-75,50\n"
        "10/08/2026;SALARIO;3500,00\n"
    )
    txns = parse_csv(raw)
    assert len(txns) == 2
    assert txns[0].posted_date == date(2026, 8, 5)
    assert txns[1].amount_cents == 350_000


def test_parse_csv_with_bank_preamble():
    raw = (
        "Extrato Conta Corrente\n"
        "Cliente: Fulano\n"
        "\n"
        "Data Lançamento;Histórico;Valor (R$)\n"
        "01/09/2026;TARIFA PACOTE;-29,90\n"
        "02/09/2026;TED RECEBIDA;1500,00\n"
    )
    txns = parse_csv(raw)
    assert len(txns) == 2
    assert "TARIFA" in txns[0].memo.upper()
    assert txns[1].direction == "credit"


def test_parse_statement_routes_ofx_and_csv():
    assert len(parse_statement(BANK_OFX.read_bytes(), filename="a.ofx")) == 3
    assert len(parse_statement(BANK_CSV.read_bytes(), filename="a.csv")) == 3
    assert len(parse_ofx(CARD_OFX.read_bytes())) == 3
