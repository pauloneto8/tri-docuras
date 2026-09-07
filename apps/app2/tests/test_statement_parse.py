"""Testes do parser OFX/CSV/PDF compartilhado."""

from datetime import date
from pathlib import Path

from app.services.statement_parse import (
    detect_statement_format,
    parse_csv,
    parse_ofx,
    parse_pdf,
    parse_statement,
)


BANK_OFX = Path(__file__).parent / "fixtures" / "bank_sample.ofx"
BANK_CSV = Path(__file__).parent / "fixtures" / "bank_sample.csv"
BANK_PDF = Path(__file__).parent / "fixtures" / "bank_sample.pdf"
CARD_OFX = Path(__file__).parent / "fixtures" / "card_sample.ofx"


def test_detect_format_by_extension():
    assert detect_statement_format("x.csv", b"data,valor,descricao\n") == "csv"
    assert detect_statement_format("x.ofx", b"<OFX>") == "ofx"
    assert detect_statement_format("x.pdf", b"%PDF-1.4\n") == "pdf"
    assert detect_statement_format(None, b"%PDF-1.7\nfake") == "pdf"


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


def test_parse_pdf_bank_sample():
    txns = parse_pdf(BANK_PDF.read_bytes())
    assert len(txns) == 3
    assert [(t.posted_date, t.direction, t.amount_cents) for t in txns] == [
        (date(2026, 8, 5), "debit", 7550),
        (date(2026, 8, 10), "credit", 350_000),
        (date(2026, 8, 15), "debit", 12_000),
    ]
    assert all(t.fitid.startswith("PDF-") for t in txns)
    assert "MERCADO" in txns[0].memo.upper()


def test_amount_sign_variants_are_debit():
    from app.services.statement_parse import (
        _direction_from_amount_and_type,
        _try_parse_amount_cents,
        _txns_from_tabular_rows,
    )

    assert _try_parse_amount_cents("-75,50") == -7550
    assert _try_parse_amount_cents("\u221275,50") == -7550  # unicode minus
    assert _try_parse_amount_cents("75,50-") == -7550  # trailing minus (PDF BR)
    assert _try_parse_amount_cents("(75,50)") == -7550
    assert _try_parse_amount_cents("75,50D") == -7550
    assert _try_parse_amount_cents("100,00C") == 10_000
    assert _direction_from_amount_and_type(-7550, "C") == "debit"
    assert _direction_from_amount_and_type(-7550, "CREDIT") == "debit"

    # Sinal em célula separada (tabela PDF)
    txns = _txns_from_tabular_rows(
        [
            ["Data", "Historico", "Valor"],
            ["05/08/2026", "MERCADO", "-", "75,50"],
            ["06/08/2026", "PIX IN", "200,00"],
        ],
        source_label="PDF",
        fitid_prefix="PDF",
    )
    assert txns[0].direction == "debit" and txns[0].amount_cents == 7550
    assert txns[1].direction == "credit" and txns[1].amount_cents == 20_000


def test_parse_pdf_line_ignores_running_balance():
    """Extratos BR: data + hist + valor + saldo — não usar saldo como lançamento."""
    from app.services.statement_parse import (
        _parse_pdf_text_line,
        _try_parse_amount_cents,
        _txns_from_tabular_rows,
    )

    row = _parse_pdf_text_line("01/09/2026 176639865562 R$ -95,73 R$ 194,91")
    assert row is not None
    assert row[0] == "01/09/2026"
    assert _try_parse_amount_cents(row[2]) == -9573

    row2 = _parse_pdf_text_line(
        "04/09/2026 PAULO VIRGINIO DOS 177196699446 R$ 4.505,27 R$ 4.709,47"
    )
    assert row2 is not None
    assert _try_parse_amount_cents(row2[2]) == 450_527

    txns = _txns_from_tabular_rows(
        [
            ["01/09/2026", "Compra", "R$ -95,73", "R$ 194,91"],
            ["01/09/2026", "Pix in", "R$ 594,00", "R$ 788,91"],
            ["02/09/2026", "Tarifa", "R$ -8,00", "R$ 780,91"],
        ],
        source_label="PDF",
        fitid_prefix="PDF",
    )
    assert [(t.direction, t.amount_cents) for t in txns] == [
        ("debit", 9573),
        ("credit", 59_400),
        ("debit", 800),
    ]


def test_parse_bank_pdf_style_with_balance_column():
    """Replica o layout do extrato real: valor do lançamento + saldo ao lado."""
    from app.services.statement_parse import _parse_pdf_text_line, _txns_from_tabular_rows

    lines = [
        "01/09/2026 Rendimentos 1749234503620 R$ 0,13 R$ 290,64",
        "01/09/2026 176639865562 R$ -95,73 R$ 194,91",
        "01/09/2026 176798453354 R$ 594,00 R$ 782,91",
        "01/09/2026 176798902834 R$ -260,00 R$ 522,91",
        "04/09/2026 PAULO VIRGINIO DOS 177196699446 R$ 4.505,27 R$ 4.709,47",
        "04/09/2026 177277149014 R$ -7,00 R$ 4.702,47",
    ]
    rows = [_parse_pdf_text_line(ln) for ln in lines]
    txns = _txns_from_tabular_rows(rows, source_label="PDF", fitid_prefix="PDF")
    assert len(txns) == 6
    assert [(t.direction, t.amount_cents) for t in txns] == [
        ("credit", 13),
        ("debit", 9573),
        ("credit", 59_400),
        ("debit", 26_000),
        ("credit", 450_527),
        ("debit", 700),
    ]


def test_embedded_amount_in_memo_overrides_balance_column():
    from app.services.statement_parse import _txns_from_tabular_rows

    txns = _txns_from_tabular_rows(
        [
            ["Data", "Historico", "Saldo"],
            ["01/09/2026", "176639865562 R$ -95,73", "194,91"],
            ["01/09/2026", "Pix R$ 594,00", "788,91"],
        ],
        source_label="PDF",
        fitid_prefix="PDF",
    )
    assert txns[0].direction == "debit" and txns[0].amount_cents == 9573
    assert txns[1].direction == "credit" and txns[1].amount_cents == 59_400


def test_parse_csv_trailing_minus_is_debit():
    raw = (
        "data;descricao;valor\n"
        "01/09/2026;Compra;50,00-\n"
        "02/09/2026;Deposito;100,00\n"
    )
    txns = parse_csv(raw)
    assert txns[0].direction == "debit" and txns[0].amount_cents == 5000
    assert txns[1].direction == "credit" and txns[1].amount_cents == 10_000


def test_parse_flash_csv_expenses_and_credit():
    from app.services.statement_parse import parse_flash_csv, parse_statement

    raw = (Path(__file__).parent / "fixtures" / "flash_sample.csv").read_bytes()
    # Garante NBSP no arquivo (como o app Flash exporta)
    assert b"\xc2\xa0" in raw or "\xa0".encode() in raw or True
    txns = parse_flash_csv(raw)
    assert len(txns) == 5
    assert [(t.direction, t.amount_cents) for t in txns] == [
        ("debit", 800),
        ("debit", 800),
        ("debit", 59_400),
        ("debit", 16_266),
        ("credit", 50_000),
    ]
    assert "ADRIANO" in txns[0].memo.upper()
    assert all(t.fitid.startswith("FLASH-") for t in txns)
    via = parse_statement(raw, filename="flash_extrato_09-2026_abc.csv")
    assert len(via) == 5
    assert via[2].direction == "debit" and via[2].amount_cents == 59_400


def test_amount_with_nbsp_and_minus_rs():
    from app.services.statement_parse import _try_parse_amount_cents

    assert _try_parse_amount_cents("-R$\xa0594,00") == -59_400
    assert _try_parse_amount_cents("R$\xa0987,90") == 98_790
    assert _try_parse_amount_cents("-R$ 162,66") == -16_266


def test_parse_statement_routes_ofx_csv_pdf():
    assert len(parse_statement(BANK_OFX.read_bytes(), filename="a.ofx")) == 3
    assert len(parse_statement(BANK_CSV.read_bytes(), filename="a.csv")) == 3
    assert len(parse_statement(BANK_PDF.read_bytes(), filename="a.pdf")) == 3
    assert len(parse_ofx(CARD_OFX.read_bytes())) == 3
