"""Parse de extratos OFX/QFX, CSV e PDF para a mesma estrutura interna."""

from __future__ import annotations

import csv
import hashlib
import io
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Literal

Direction = Literal["debit", "credit"]
StatementFormat = Literal["ofx", "csv", "pdf"]

_STMTTRN_RE = re.compile(r"<STMTTRN>(.*?)</STMTTRN>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(
    r"<(FITID|DTPOSTED|TRNAMT|TRNTYPE|MEMO|NAME|CHECKNUM)>([^<\r\n]+)",
    re.IGNORECASE,
)

# Boosts quando há cabeçalho reconhecível (opcional — a análise por conteúdo manda).
_CSV_DATE_ALIASES = {
    "data",
    "date",
    "posted_date",
    "posted",
    "dtposted",
    "data_lancamento",
    "data_lanc",
    "data_movimento",
    "data_transacao",
    "data_transação",
    "dt",
}
_CSV_AMOUNT_ALIASES = {
    "valor",
    "amount",
    "trnamt",
    "value",
    "montante",
    "vlr",
    "valor_rs",
    "quantidade",
}
_CSV_MEMO_ALIASES = {
    "descricao",
    "descrição",
    "description",
    "memo",
    "historico",
    "histórico",
    "name",
    "lancamento",
    "lançamento",
    "detalhe",
    "detalhes",
    "estabelecimento",
    "favorecido",
    "titulo",
    "título",
    "movimentacao",
    "movimentação",
    "movimento",
    "local",
    "comercio",
    "comércio",
}
_CSV_FITID_ALIASES = {
    "fitid",
    "id",
    "referencia",
    "referência",
    "ref",
    "external_id",
    "identificador",
    "documento",
    "doc",
    "nsu",
}
_CSV_TYPE_ALIASES = {
    "tipo",
    "type",
    "trntype",
    "direction",
    "direcao",
    "direção",
    "natureza",
    "dc",
    "c_d",
    "forma",
    "meio",
    "pagamento",
    "forma_pagamento",
    "canal",
}
_CSV_DEBIT_ALIASES = {
    "debito",
    "débito",
    "debit",
    "saida",
    "saída",
    "despesa",
    "compra",
}
_CSV_CREDIT_ALIASES = {
    "credito",
    "crédito",
    "credit",
    "entrada",
    "receita",
    "deposito",
    "depósito",
    "cashback",
    "rendimento",
}
_CSV_BALANCE_ALIASES = {
    "saldo",
    "balance",
    "saldo_atual",
    "saldo_final",
    "running_balance",
    "saldo_conta",
    "saldo_disponivel",
    "available_balance",
}
_CSV_HOUR_ALIASES = {"hora", "horario", "horário", "time", "hora_movimento"}

# Valores monetários em texto de PDF/CSV (com ou sem R$).
_AMOUNT_TOKEN_RE = re.compile(
    r"(?:R\$\s*)?"
    r"(?:"
    r"\(\s*[-−–—]?\s*\d{1,3}(?:\.\d{3})*,\d{2}\s*\)"
    r"|\(\s*[-−–—]?\s*\d+[.,]\d{2}\s*\)"
    r"|[-−–—]\s*\d{1,3}(?:\.\d{3})*,\d{2}"
    r"|[-−–—]\s*\d+[.,]\d{2}"
    r"|\d{1,3}(?:\.\d{3})*,\d{2}\s*[-−–—]"
    r"|\d+[.,]\d{2}\s*[-−–—]"
    r"|\d{1,3}(?:\.\d{3})*,\d{2}"
    r"|\d+[.,]\d{2}"
    r")",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class OfxTxn:
    fitid: str
    posted_date: date
    amount_cents: int
    direction: Direction
    memo: str
    trntype: str


@dataclass
class _CsvLayout:
    date_idx: int
    amount_idx: int | None
    memo_idx: int
    fitid_idx: int | None = None
    type_idx: int | None = None
    debit_idx: int | None = None
    credit_idx: int | None = None
    header_names: list[str] | None = None


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_memo(text: str) -> str:
    cleaned = _strip_accents(text or "").lower()
    cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _normalize_header(name: str) -> str:
    return normalize_memo(name).replace(" ", "_")


def _decode_text(content: str | bytes) -> str:
    if isinstance(content, str):
        return content.replace("\x00", "")
    for encoding in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            return content.decode(encoding).replace("\x00", "")
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace").replace("\x00", "")


def _parse_ofx_date(raw: str) -> date:
    digits = re.sub(r"[^0-9]", "", raw.strip())
    if len(digits) < 8:
        raise ValueError(f"Data OFX inválida: {raw!r}")
    return date(int(digits[0:4]), int(digits[4:6]), int(digits[6:8]))


def _normalize_dash_chars(text: str) -> str:
    """Unifica hífens/menos tipográficos (comuns em PDF) em '-' ASCII."""
    out = text or ""
    for ch in ("\u2212", "\u2013", "\u2014", "\ufe63", "\uff0d"):
        out = out.replace(ch, "-")
    return out


def _try_parse_date(raw: str) -> date | None:
    text = (raw or "").strip()
    if not text or len(text) > 32:
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%Y/%m/%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    digits = re.sub(r"[^0-9]", "", text)
    if len(digits) == 8:
        try:
            if digits[:2] in {"19", "20"}:
                return date(int(digits[0:4]), int(digits[4:6]), int(digits[6:8]))
            return date(int(digits[4:8]), int(digits[2:4]), int(digits[0:2]))
        except ValueError:
            return None
    return None


def _parse_flexible_date(raw: str) -> date:
    parsed = _try_parse_date(raw)
    if parsed is None:
        raise ValueError(f"Data inválida no CSV: {raw!r}")
    return parsed


def _normalize_money_text(text: str) -> str:
    """Remove NBSP e espaços tipográficos comuns em CSV Flash/bancos."""
    out = text or ""
    for ch in ("\xa0", "\u00a0", "\u202f", "\u2007", "\u2009"):
        out = out.replace(ch, " ")
    return out


def _try_parse_amount_cents(raw: str) -> int | None:
    text = _normalize_money_text(_normalize_dash_chars(raw or "")).strip()
    if not text:
        return None
    # Evita tratar datas DD/MM/YYYY como valor
    if _try_parse_date(text) is not None and re.fullmatch(r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}", text):
        return None
    cleaned = (
        text.replace(" ", "")
        .replace("R$", "")
        .replace("r$", "")
        .replace("RS", "")
        .replace("rs", "")
    )
    # Sufixo D/C às vezes vem grudado no valor (PDF BR)
    dc_suffix = ""
    dc_match = re.fullmatch(r"(.+?)([DdCc])", cleaned)
    if dc_match and re.search(r"\d", dc_match.group(1)):
        cleaned, dc_suffix = dc_match.group(1), dc_match.group(2).upper()

    negative = False
    if cleaned.startswith("(") and cleaned.endswith(")"):
        negative = True
        cleaned = cleaned[1:-1]
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]
    if cleaned.startswith("-"):
        negative = True
        cleaned = cleaned[1:]
    elif cleaned.endswith("-"):
        # Formato bancário frequente em PDF: 75,50-
        negative = True
        cleaned = cleaned[:-1]
    if not cleaned or not re.search(r"\d", cleaned):
        return None
    # Só dígitos + separadores decimais/milhar
    if not re.fullmatch(r"[\d.,]+", cleaned):
        return None
    # IDs de extrato (10–15 dígitos) não são valores monetários
    if re.fullmatch(r"\d{8,}", cleaned):
        return None
    try:
        if "," in cleaned and "." in cleaned:
            if cleaned.rfind(",") > cleaned.rfind("."):
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                cleaned = cleaned.replace(",", "")
        elif "," in cleaned:
            # 1.234 ou 12,34 — se houver exatamente 3 dígitos após vírgula sem ponto, raro; assume decimal BR
            parts = cleaned.split(",")
            if len(parts) == 2 and len(parts[1]) <= 2:
                cleaned = cleaned.replace(",", ".")
            elif len(parts) == 2 and len(parts[1]) == 3 and "." not in cleaned:
                # 1,234 milhar ambíguo → trata como milhar se parte inteira > 0
                cleaned = cleaned.replace(",", "")
            else:
                cleaned = cleaned.replace(",", ".")
        value = float(cleaned)
    except ValueError:
        return None
    cents = int(round(abs(value) * 100))
    if dc_suffix == "D":
        negative = True
    elif dc_suffix == "C":
        negative = False
    if cents == 0 and not negative and value == 0:
        return 0
    return -cents if negative or value < 0 else cents


def _parse_amount_to_cents(raw: str) -> int:
    parsed = _try_parse_amount_cents(raw)
    if parsed is None:
        raise ValueError(f"Valor vazio ou inválido: {raw!r}")
    return parsed


def _direction_from_amount_and_type(signed_cents: int, trntype: str) -> Direction:
    """Direção do movimento: sinal do valor tem prioridade sobre rótulos ambíguos."""
    t = _strip_accents(trntype or "").upper().strip()
    credit_types = {
        "CREDIT",
        "DEP",
        "DIRECTDEP",
        "PAYMENT",
        "XFER",
        "C",
        "CREDITO",
        "ENTRADA",
        "RECEITA",
        "INCOME",
        "CR",
    }
    debit_types = {
        "DEBIT",
        "POS",
        "ATM",
        "CHECK",
        "FEE",
        "SRVCHG",
        "D",
        "DEBITO",
        "SAIDA",
        "DESPESA",
        "EXPENSE",
        "DB",
    }
    # Valor negativo = saída, mesmo se o PDF trouxer um "C" espúrio na linha
    if signed_cents < 0:
        return "debit"
    if t in debit_types:
        return "debit"
    if t in credit_types:
        return "credit"
    if signed_cents > 0:
        return "credit"
    return "debit"


def _synthetic_fitid(
    posted: date,
    amount_cents: int,
    memo: str,
    index: int,
    *,
    prefix: str = "CSV",
) -> str:
    raw = f"{posted.isoformat()}|{amount_cents}|{normalize_memo(memo)}|{index}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}-{digest}"


def detect_statement_format(
    filename: str | None, content: str | bytes
) -> StatementFormat:
    name = (filename or "").lower()
    suffix = Path(name).suffix
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".csv", ".txt"}:
        return "csv"
    if suffix in {".ofx", ".qfx"}:
        return "ofx"
    if isinstance(content, (bytes, bytearray)) and bytes(content[:5]) == b"%PDF-":
        return "pdf"
    text = _decode_text(content)[:4000].upper()
    if "<OFX" in text or "<STMTTRN" in text or "OFXHEADER" in text:
        return "ofx"
    if "," in text or ";" in text or "\t" in text:
        return "csv"
    raise ValueError(
        "Formato não reconhecido. Envie um arquivo OFX/QFX, CSV ou PDF (texto)."
    )


def parse_ofx(content: str | bytes) -> list[OfxTxn]:
    text = _decode_text(content)
    blocks = _STMTTRN_RE.findall(text)
    if not blocks:
        parts = re.split(r"<STMTTRN>", text, flags=re.IGNORECASE)
        blocks = parts[1:] if len(parts) > 1 else []

    txns: list[OfxTxn] = []
    seen_fitids: set[str] = set()
    for block in blocks:
        fields: dict[str, str] = {}
        for match in _TAG_RE.finditer(block):
            fields[match.group(1).upper()] = match.group(2).strip()
        fitid = fields.get("FITID") or fields.get("CHECKNUM")
        if not fitid or fitid in seen_fitids:
            continue
        raw_date = fields.get("DTPOSTED")
        raw_amt = fields.get("TRNAMT")
        if not raw_date or raw_amt is None:
            continue
        signed = _parse_amount_to_cents(raw_amt)
        if signed == 0:
            continue
        trntype = fields.get("TRNTYPE", "")
        direction = _direction_from_amount_and_type(signed, trntype)
        memo = (fields.get("MEMO") or fields.get("NAME") or "Movimento OFX").strip()[:255]
        seen_fitids.add(fitid)
        txns.append(
            OfxTxn(
                fitid=fitid[:128],
                posted_date=_parse_ofx_date(raw_date),
                amount_cents=abs(signed),
                direction=direction,
                memo=memo,
                trntype=trntype.upper(),
            )
        )
    if not txns:
        raise ValueError("Nenhuma transação encontrada no arquivo OFX.")
    return txns


def _sniff_delimiter(sample: str) -> str:
    """Detecta delimitador; TAB tem prioridade (CSV Flash / exportações modernas)."""
    lines = [ln for ln in sample.splitlines() if ln.strip()][:8]
    if not lines:
        return ","
    semi = sum(ln.count(";") for ln in lines)
    tabs = sum(ln.count("\t") for ln in lines)
    pipes = sum(ln.count("|") for ln in lines)
    commas = sum(ln.count(",") for ln in lines)
    if tabs > 0 and tabs >= max(semi, commas, pipes):
        return "\t"
    # Ponto e vírgula é o padrão brasileiro de extrato
    if semi > 0 and semi >= max(tabs, pipes):
        return ";"
    if pipes > 0 and pipes >= commas:
        return "|"
    if commas > 0:
        return ","
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t|")
        return dialect.delimiter
    except csv.Error:
        return ","


def _read_matrix(text: str) -> tuple[str, list[list[str]]]:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return ",", []
    sample = "\n".join(lines[: min(12, len(lines))])
    delimiter = _sniff_delimiter(sample)
    reader = csv.reader(io.StringIO("\n".join(lines)), delimiter=delimiter)
    rows: list[list[str]] = []
    for row in reader:
        cells = [(c or "").strip() for c in row]
        if any(cells):
            rows.append(cells)
    return delimiter, rows


def _header_alias_score(name: str, aliases: set[str]) -> float:
    key = _normalize_header(name)
    if not key:
        return 0.0
    if key in {_normalize_header(a) for a in aliases}:
        return 3.0
    for alias in aliases:
        na = _normalize_header(alias)
        if na and (na in key or key in na):
            return 1.5
    return 0.0


def _looks_like_header_row(row: list[str]) -> bool:
    if not row:
        return False
    date_hits = sum(1 for c in row if _try_parse_date(c) is not None)
    amount_hits = sum(1 for c in row if _try_parse_amount_cents(c) is not None)
    # Cabeçalho típico: poucas datas/valores parseáveis + texto curto
    if date_hits >= 1 and amount_hits >= 1:
        return False
    alias_hits = 0
    for cell in row:
        alias_hits += _header_alias_score(cell, _CSV_DATE_ALIASES) > 0
        alias_hits += _header_alias_score(cell, _CSV_AMOUNT_ALIASES) > 0
        alias_hits += _header_alias_score(cell, _CSV_MEMO_ALIASES) > 0
        alias_hits += _header_alias_score(cell, _CSV_DEBIT_ALIASES) > 0
        alias_hits += _header_alias_score(cell, _CSV_CREDIT_ALIASES) > 0
    if alias_hits >= 2:
        return True
    # Linha só com palavras (sem números dominantes)
    alphaish = sum(1 for c in row if c and re.search(r"[A-Za-zÀ-ÿ]", c) and _try_parse_amount_cents(c) is None)
    return alphaish >= max(2, len(row) // 2) and date_hits == 0 and amount_hits == 0


def _row_data_score(row: list[str]) -> float:
    if not row:
        return 0.0
    score = 0.0
    has_date = False
    has_amount = False
    for cell in row:
        if _try_parse_date(cell) is not None:
            score += 2.0
            has_date = True
        elif _try_parse_amount_cents(cell) is not None:
            score += 1.5
            has_amount = True
        elif cell and re.search(r"[A-Za-zÀ-ÿ]", cell):
            score += 0.4
    if has_date and has_amount:
        score += 2.0
    return score


def _find_table_start(rows: list[list[str]]) -> int:
    """Pula preâmbulo (título do banco) e acha início da tabela de movimentos."""
    if not rows:
        return 0
    # Preferir cabeçalho reconhecível seguido de linha de dados
    for i in range(min(12, len(rows) - 1)):
        if _looks_like_header_row(rows[i]) and _row_data_score(rows[i + 1]) >= 2.0:
            return i

    # Primeira sequência de linhas com cara de lançamento (data + valor).
    # Evita o antigo maximizador por janela, que preferia o fim do arquivo.
    for i, row in enumerate(rows):
        if _row_data_score(row) < 3.0:
            continue
        follow = rows[i : i + 3]
        ok = sum(1 for r in follow if _row_data_score(r) >= 3.0)
        if ok >= min(2, len(follow)):
            return i
    return 0


def _analyze_columns(
    data_rows: list[list[str]],
    header: list[str] | None,
) -> _CsvLayout:
    if not data_rows:
        raise ValueError("Não foi possível localizar linhas de movimento no CSV.")

    width = max(len(r) for r in data_rows)
    # Pad rows
    matrix = [r + [""] * (width - len(r)) for r in data_rows]
    sample = matrix[: min(40, len(matrix))]

    date_scores = [0.0] * width
    amount_scores = [0.0] * width
    memo_scores = [0.0] * width
    fitid_scores = [0.0] * width
    type_scores = [0.0] * width
    debit_scores = [0.0] * width
    credit_scores = [0.0] * width
    balance_scores = [0.0] * width

    if header:
        header = header + [""] * (width - len(header))
        for i, name in enumerate(header[:width]):
            date_scores[i] += _header_alias_score(name, _CSV_DATE_ALIASES)
            amount_scores[i] += _header_alias_score(name, _CSV_AMOUNT_ALIASES)
            memo_scores[i] += _header_alias_score(name, _CSV_MEMO_ALIASES)
            fitid_scores[i] += _header_alias_score(name, _CSV_FITID_ALIASES)
            type_scores[i] += _header_alias_score(name, _CSV_TYPE_ALIASES)
            debit_scores[i] += _header_alias_score(name, _CSV_DEBIT_ALIASES)
            credit_scores[i] += _header_alias_score(name, _CSV_CREDIT_ALIASES)
            balance_scores[i] += _header_alias_score(name, _CSV_BALANCE_ALIASES)

    for row in sample:
        for i, cell in enumerate(row):
            if not cell:
                continue
            if _try_parse_date(cell) is not None:
                date_scores[i] += 1.0
            amt = _try_parse_amount_cents(cell)
            if amt is not None:
                amount_scores[i] += 1.0
                if amt < 0:
                    debit_scores[i] += 0.15
                elif amt > 0:
                    credit_scores[i] += 0.15
            # Texto descritivo (evita IDs tipo CSV-XXX-001)
            looks_like_id = bool(
                re.fullmatch(r"[A-Za-z0-9\-_./]{4,40}", cell)
                and " " not in cell
                and _try_parse_date(cell) is None
                and amt is None
            )
            if (
                re.search(r"[A-Za-zÀ-ÿ]", cell)
                and _try_parse_date(cell) is None
                and amt is None
                and not looks_like_id
            ):
                memo_scores[i] += min(len(cell), 40) / 20.0
                if " " in cell:
                    memo_scores[i] += 0.5
            if looks_like_id:
                fitid_scores[i] += 0.5
            # Tipo D/C
            if _normalize_header(cell) in {"d", "c", "debito", "credito", "despesa", "receita"}:
                type_scores[i] += 1.0

    # Colunas só positivas vs só negativas → débito/crédito separados
    for i in range(width):
        values = [_try_parse_amount_cents(r[i]) for r in sample if i < len(r)]
        values = [v for v in values if v is not None and v != 0]
        if len(values) >= 2 and all(v > 0 for v in values):
            credit_scores[i] += 1.0
            # Coluna sempre positiva e “grande” costuma ser saldo, não valor
            if balance_scores[i] == 0 and len(values) >= 3:
                balance_scores[i] += 0.5
        if len(values) >= 2 and all(v < 0 for v in values):
            debit_scores[i] += 1.0
        # Coluna de valor “mista” (sinais diferentes) é melhor como amount único
        if len(values) >= 2 and any(v > 0 for v in values) and any(v < 0 for v in values):
            amount_scores[i] += 3.0
            balance_scores[i] -= 2.0

    # Não usar coluna de saldo como valor do lançamento
    for i in range(width):
        if balance_scores[i] >= 1.0:
            amount_scores[i] -= 5.0
            credit_scores[i] -= 2.0
            debit_scores[i] -= 2.0

    date_idx = max(range(width), key=lambda i: date_scores[i])
    if date_scores[date_idx] < 1.0:
        raise ValueError(
            "Não identifiquei uma coluna de data no arquivo. "
            "Verifique se o extrato contém datas no formato DD/MM/AAAA."
        )

    memo_idx = max(range(width), key=lambda i: memo_scores[i] if i != date_idx else -1)
    if memo_scores[memo_idx] < 0.5:
        # fallback: maior coluna textual restante
        candidates = [i for i in range(width) if i != date_idx]
        if not candidates:
            raise ValueError("Não identifiquei a descrição dos lançamentos no CSV.")
        memo_idx = max(candidates, key=lambda i: sum(len(r[i]) for r in sample if i < len(r)))

    # Prefer amount único; senão par débito/crédito
    amount_idx: int | None = None
    debit_idx: int | None = None
    credit_idx: int | None = None
    used = {date_idx, memo_idx}

    debit_ranked = sorted(
        (i for i in range(width) if i not in used),
        key=lambda i: debit_scores[i],
        reverse=True,
    )
    credit_ranked = sorted(
        (i for i in range(width) if i not in used),
        key=lambda i: credit_scores[i],
        reverse=True,
    )
    # Cabeçalhos claros de débito+crédito têm prioridade sobre "valor" único
    split_debit_credit = (
        debit_ranked
        and credit_ranked
        and debit_ranked[0] != credit_ranked[0]
        and debit_scores[debit_ranked[0]] >= 1.5
        and credit_scores[credit_ranked[0]] >= 1.5
    )

    amount_ranked = sorted(
        (i for i in range(width) if i not in used),
        key=lambda i: amount_scores[i],
        reverse=True,
    )

    if split_debit_credit:
        debit_idx = debit_ranked[0]
        credit_idx = credit_ranked[0]
        used.update({debit_idx, credit_idx})
    elif amount_ranked and amount_scores[amount_ranked[0]] >= 1.0:
        amount_idx = amount_ranked[0]
        used.add(amount_idx)
    elif (
        debit_ranked
        and credit_ranked
        and debit_scores[debit_ranked[0]] >= 0.8
        and credit_scores[credit_ranked[0]] >= 0.8
        and debit_ranked[0] != credit_ranked[0]
    ):
        debit_idx = debit_ranked[0]
        credit_idx = credit_ranked[0]
        used.update({debit_idx, credit_idx})
    elif amount_ranked:
        amount_idx = amount_ranked[0]
        used.add(amount_idx)
    else:
        raise ValueError(
            "Não identifiquei a coluna de valor no arquivo. "
            "O extrato precisa de um valor por linha (ou débitos/créditos)."
        )

    fitid_idx = None
    fitid_ranked = sorted(
        (i for i in range(width) if i not in used),
        key=lambda i: fitid_scores[i],
        reverse=True,
    )
    if fitid_ranked and fitid_scores[fitid_ranked[0]] >= 0.8:
        fitid_idx = fitid_ranked[0]
        used.add(fitid_idx)

    type_idx = None
    type_ranked = sorted(
        (i for i in range(width) if i not in used),
        key=lambda i: type_scores[i],
        reverse=True,
    )
    if type_ranked and type_scores[type_ranked[0]] >= 1.0:
        type_idx = type_ranked[0]

    return _CsvLayout(
        date_idx=date_idx,
        amount_idx=amount_idx,
        memo_idx=memo_idx,
        fitid_idx=fitid_idx,
        type_idx=type_idx,
        debit_idx=debit_idx,
        credit_idx=credit_idx,
        header_names=header,
    )


def _cell(row: list[str], idx: int | None) -> str:
    if idx is None or idx >= len(row):
        return ""
    return (row[idx] or "").strip()


def _txns_from_tabular_rows(
    rows: list[list[str]],
    *,
    source_label: str = "CSV",
    fitid_prefix: str = "CSV",
) -> list[OfxTxn]:
    """Converte matriz tabular (CSV ou tabela/linhas de PDF) em OfxTxn."""
    rows = _prepare_matrix_rows(rows)
    if not rows:
        raise ValueError(f"Arquivo {source_label} vazio.")

    start = _find_table_start(rows)
    table = rows[start:]
    if not table:
        raise ValueError(f"Não encontrei a tabela de movimentos no arquivo {source_label}.")

    header: list[str] | None = None
    data_rows = table
    if _looks_like_header_row(table[0]):
        header = table[0]
        data_rows = table[1:]
    if not data_rows:
        raise ValueError(f"{source_label} só tem cabeçalho, sem lançamentos.")

    widths = [len(r) for r in data_rows if len(r) >= 2]
    if not widths:
        raise ValueError(f"Linhas do {source_label} não têm colunas suficientes.")
    target_width = max(set(widths), key=widths.count)
    data_rows = [r for r in data_rows if len(r) >= max(2, target_width - 1)]
    if not data_rows:
        raise ValueError(f"Não encontrei linhas de movimento utilizáveis no {source_label}.")

    layout = _analyze_columns(data_rows, header)

    txns: list[OfxTxn] = []
    seen_fitids: set[str] = set()
    for index, row in enumerate(data_rows, start=1):
        raw_date = _cell(row, layout.date_idx)
        memo = _cell(row, layout.memo_idx)
        if not raw_date and not memo:
            continue
        posted = _try_parse_date(raw_date)
        if posted is None:
            continue
        memo = (memo or f"Movimento {source_label}")[:255]

        signed = 0
        trntype = ""
        if layout.amount_idx is not None:
            raw_amt = _cell(row, layout.amount_idx)
            if not raw_amt:
                continue
            amt = _try_parse_amount_cents(raw_amt)
            if amt is None:
                continue
            signed = amt
            if layout.type_idx is not None:
                trntype = _cell(row, layout.type_idx)
        else:
            raw_debit = _cell(row, layout.debit_idx)
            raw_credit = _cell(row, layout.credit_idx)
            debit_amt = _try_parse_amount_cents(raw_debit) if raw_debit else None
            credit_amt = _try_parse_amount_cents(raw_credit) if raw_credit else None
            if debit_amt and credit_amt:
                continue
            if debit_amt:
                signed = -abs(debit_amt)
                trntype = "DEBIT"
            elif credit_amt:
                signed = abs(credit_amt)
                trntype = "CREDIT"
            else:
                continue

        # PDF/CSV: valor real às vezes fica no histórico (R$ -95,73) e a coluna
        # escolhida é o saldo. Prefere o valor embutido quando fizer sentido.
        embedded = _amount_from_embedded_text(memo)
        if embedded is not None and embedded != 0:
            if abs(embedded) != abs(signed) and (
                embedded < 0
                or (signed > 0 and abs(embedded) < abs(signed))
            ):
                # Limpa o valor do memo para não poluir a descrição
                cleaned_memo = _AMOUNT_TOKEN_RE.sub("", memo)
                cleaned_memo = re.sub(r"\s{2,}", " ", cleaned_memo).strip(" -|")
                cleaned_memo = re.sub(r"\s+\d{8,}\s*$", "", cleaned_memo).strip()
                if cleaned_memo:
                    memo = cleaned_memo[:255]
                signed = embedded

        if signed == 0:
            continue
        direction = _direction_from_amount_and_type(signed, trntype)
        amount_cents = abs(signed)
        raw_fitid = _cell(row, layout.fitid_idx)
        fitid = (
            raw_fitid
            or _synthetic_fitid(
                posted, amount_cents, memo, index, prefix=fitid_prefix
            )
        )[:128]
        if fitid in seen_fitids:
            fitid = f"{fitid}-{index}"[:128]
        seen_fitids.add(fitid)
        txns.append(
            OfxTxn(
                fitid=fitid,
                posted_date=posted,
                amount_cents=amount_cents,
                direction=direction,
                memo=memo,
                trntype=(trntype or direction).upper()[:32],
            )
        )

    if not txns:
        raise ValueError(
            f"Nenhuma transação encontrada no arquivo {source_label}. "
            "Confira se há linhas com data e valor."
        )
    return txns


def parse_csv(content: str | bytes) -> list[OfxTxn]:
    """Importa CSV 'como está': detecta delimitador, preâmbulo e colunas.

    Não exige nomes fixos de cabeçalho. Analisa o conteúdo para achar
    data, valor (ou débito/crédito) e descrição.
    """
    text = _decode_text(content).strip()
    if not text:
        raise ValueError("Arquivo CSV vazio.")

    _delimiter, rows = _read_matrix(text)
    if not rows:
        raise ValueError("Arquivo CSV vazio.")
    return _txns_from_tabular_rows(rows, source_label="CSV", fitid_prefix="CSV")


def _is_flash_statement(filename: str | None, text: str) -> bool:
    name = (filename or "").lower()
    if "flash" in name:
        return True
    head = _strip_accents(_normalize_money_text(text[:3000])).lower()
    has_data = "data" in head
    has_hora = "hora" in head
    has_mov = "moviment" in head or "estabelecimento" in head
    has_saldo = "saldo" in head
    has_valor = "valor" in head
    return has_data and has_hora and has_valor and (has_mov or has_saldo)


def _flash_fix_mojibake(text: str) -> str:
    """Corrige UTF-8 lido como Latin-1 (CartÃ£o → Cartão) quando aplicável."""
    if "Ã" not in text and "Â" not in text:
        return text
    try:
        fixed = text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text
    # Só aceita se melhorou acentos comuns
    if fixed.count("ã") + fixed.count("á") + fixed.count("é") >= text.count("Ã"):
        return fixed
    return text


def parse_flash_csv(content: str | bytes) -> list[OfxTxn]:
    """Parser do extrato pessoal Flash (CSV/TSV do app).

    Layout típico:
    Data | Hora | Movimentação | Valor (-R$ x,xx) | Tipo (Cartão/PIX) | Saldo
    """
    text = _flash_fix_mojibake(_normalize_money_text(_decode_text(content))).strip()
    if not text:
        raise ValueError("Arquivo Flash vazio.")

    # Flash costuma ser TAB; força TAB se houver
    if "\t" in text.splitlines()[0] if text.splitlines() else False:
        rows = [
            [c.strip() for c in line.split("\t")]
            for line in text.splitlines()
            if line.strip()
        ]
    else:
        _delim, rows = _read_matrix(text)
    if not rows:
        raise ValueError("Arquivo Flash vazio.")

    # Localiza cabeçalho
    header_idx = None
    for i, row in enumerate(rows[:15]):
        joined = " ".join(_normalize_header(c) for c in row)
        if "data" in joined and ("valor" in joined or "saldo" in joined):
            header_idx = i
            break
    if header_idx is None:
        # Fallback: análise genérica (já trata saldo / NBSP)
        return _txns_from_tabular_rows(rows, source_label="Flash", fitid_prefix="FLASH")

    header = rows[header_idx]
    data_rows = rows[header_idx + 1 :]
    norm = [_normalize_header(h) for h in header]

    def _col(aliases: set[str]) -> int | None:
        best_i, best = None, 0.0
        for i, name in enumerate(norm):
            score = _header_alias_score(name, aliases)
            if score > best:
                best, best_i = score, i
        return best_i if best > 0 else None

    date_idx = _col(_CSV_DATE_ALIASES)
    memo_idx = _col(_CSV_MEMO_ALIASES)
    amount_idx = _col(_CSV_AMOUNT_ALIASES)
    balance_idx = _col(_CSV_BALANCE_ALIASES)
    type_idx = _col(_CSV_TYPE_ALIASES)
    hour_idx = _col(_CSV_HOUR_ALIASES)

    if date_idx is None or amount_idx is None:
        return _txns_from_tabular_rows(
            rows[header_idx:], source_label="Flash", fitid_prefix="FLASH"
        )
    if memo_idx is None:
        # Usa a maior coluna textual que não seja data/valor/saldo/hora
        used = {date_idx, amount_idx, balance_idx, type_idx, hour_idx} - {None}
        candidates = [i for i in range(len(header)) if i not in used]
        if not candidates:
            raise ValueError("Não identifiquei a descrição no extrato Flash.")
        memo_idx = max(
            candidates,
            key=lambda i: sum(len(r[i]) for r in data_rows[:40] if i < len(r)),
        )

    # Garante que valor ≠ saldo
    if balance_idx is not None and amount_idx == balance_idx:
        # Escolhe outra coluna monetária
        for i, name in enumerate(norm):
            if i == balance_idx:
                continue
            if _header_alias_score(name, _CSV_AMOUNT_ALIASES) > 0:
                amount_idx = i
                break

    txns: list[OfxTxn] = []
    seen: set[str] = set()
    for index, row in enumerate(data_rows, start=1):
        raw_date = _cell(row, date_idx)
        posted = _try_parse_date(raw_date)
        if posted is None:
            continue
        memo = (_cell(row, memo_idx) or "Movimento Flash").strip()[:255]
        raw_amt = _cell(row, amount_idx)
        signed = _try_parse_amount_cents(raw_amt)
        if signed is None or signed == 0:
            continue
        # Se a coluna de valor veio vazia/errada e há valor embutido no memo
        if abs(signed) > 0 and balance_idx is not None and amount_idx == balance_idx:
            embedded = _amount_from_embedded_text(memo)
            if embedded is not None:
                signed = embedded
        trntype = _cell(row, type_idx) if type_idx is not None else ""
        # Meio Cartão/PIX não define direção — o sinal do valor manda
        if _normalize_header(trntype) in {"cartao", "pix", "pagamento", "transferencia"}:
            trntype = ""
        direction = _direction_from_amount_and_type(signed, trntype)
        amount_cents = abs(signed)
        fitid = _synthetic_fitid(
            posted, amount_cents, memo, index, prefix="FLASH"
        )[:128]
        if fitid in seen:
            fitid = f"{fitid}-{index}"[:128]
        seen.add(fitid)
        txns.append(
            OfxTxn(
                fitid=fitid,
                posted_date=posted,
                amount_cents=amount_cents,
                direction=direction,
                memo=memo,
                trntype=(trntype or direction).upper()[:32],
            )
        )

    if not txns:
        raise ValueError(
            "Nenhuma transação encontrada no extrato Flash. "
            "Confira se o CSV tem colunas Data, Movimentação e Valor."
        )
    return txns


_PDF_LINE_RE = re.compile(
    r"^(?P<date>\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})\s+"
    r"(?P<rest>.+)$"
)


def _iter_amount_tokens(text: str) -> list[re.Match[str]]:
    return list(_AMOUNT_TOKEN_RE.finditer(_normalize_dash_chars(text or "")))


def _pick_transaction_amount_match(
    matches: list[re.Match[str]],
) -> re.Match[str] | None:
    """Em extratos BR, o último valor costuma ser saldo; o penúltimo é o lançamento."""
    parsed: list[tuple[re.Match[str], int]] = []
    for match in matches:
        cents = _try_parse_amount_cents(match.group(0))
        if cents is not None and cents != 0:
            parsed.append((match, cents))
    if not parsed:
        for match in matches:
            cents = _try_parse_amount_cents(match.group(0))
            if cents is not None:
                return match
        return None
    if len(parsed) == 1:
        return parsed[0][0]
    body = parsed[:-1]  # exclui saldo final
    for match, cents in body:
        if cents < 0:
            return match
    # Sem negativo no corpo: usa o penúltimo (valor); último = saldo
    return body[-1][0]


def _amount_from_embedded_text(text: str) -> int | None:
    """Extrai valor do lançamento quando ele veio misturado no histórico (PDF)."""
    matches = _iter_amount_tokens(text)
    if not matches:
        return None
    picked = _pick_transaction_amount_match(matches)
    if picked is None:
        return None
    return _try_parse_amount_cents(picked.group(0))


def _parse_pdf_text_line(line: str) -> list[str] | None:
    """Converte linha de extrato PDF em [data, memo, valor].

    Padrão comum: data | histórico | valor | saldo.
    O regex antigo pegava o saldo (último número) como valor — corrigido aqui.
    """
    line = _normalize_dash_chars(line).strip()
    if not line:
        return None
    match = _PDF_LINE_RE.match(line)
    if not match:
        return None
    date_s = match.group("date")
    rest = match.group("rest").strip()
    amount_matches = _iter_amount_tokens(rest)
    if not amount_matches:
        return None
    picked = _pick_transaction_amount_match(amount_matches)
    if picked is None:
        return None
    amount_raw = picked.group(0).replace(" ", "")
    memo = rest[: picked.start()].strip()
    # Remove IDs numéricos longos soltos no fim do memo (mantém descrição)
    memo = re.sub(r"\s+\d{8,}\s*$", "", memo).strip()
    if not memo:
        # Sem descrição textual — usa o trecho antes do valor (pode ser só ID)
        memo = rest[: picked.start()].strip() or "Movimento PDF"
    # Sufixo D/C após o valor
    tail = rest[picked.end() :].strip()
    dc = ""
    dc_match = re.match(r"^(D|C|DEB(?:ITO)?|CRED(?:ITO)?)\b", tail, re.IGNORECASE)
    if dc_match and len(amount_matches) == 1:
        dc = dc_match.group(1).upper()[:1]
    cells = [date_s, memo, amount_raw]
    if dc:
        cells.append(dc)
    return cells


def _merge_sign_cells(row: list[str]) -> list[str]:
    """Junta '-' sozinho com a célula seguinte (tabelas PDF costumam separar o sinal)."""
    out: list[str] = []
    i = 0
    while i < len(row):
        cell = _normalize_dash_chars((row[i] or "").strip())
        nxt = _normalize_dash_chars((row[i + 1] or "").strip()) if i + 1 < len(row) else ""
        if cell in {"-", "−", "–"} and nxt and _try_parse_amount_cents(nxt) is not None:
            out.append(f"-{nxt.lstrip('+-')}")
            i += 2
            continue
        # Valor depois do sinal colado na descrição: "... EXTRA -" | "75,50"
        if cell.endswith("-") and nxt and _try_parse_amount_cents(nxt) is not None:
            if _try_parse_amount_cents(cell) is None:
                out.append(cell[:-1].rstrip())
                out.append(f"-{nxt.lstrip('+-')}")
                i += 2
                continue
        out.append(row[i])
        i += 1
    return out


def _prepare_matrix_rows(rows: list[list[str]]) -> list[list[str]]:
    prepared: list[list[str]] = []
    for row in rows:
        cells = [_normalize_dash_chars((c or "").strip()) for c in row]
        cells = _merge_sign_cells(cells)
        if any(cells):
            prepared.append(cells)
    return prepared


def _rows_from_pdf_tables(pdf: object) -> list[list[str]]:
    rows: list[list[str]] = []
    for page in getattr(pdf, "pages", []):
        tables = page.extract_tables() or []
        for table in tables:
            for raw_row in table or []:
                if not raw_row:
                    continue
                cells = [
                    re.sub(r"\s+", " ", (c or "").replace("\n", " ")).strip()
                    for c in raw_row
                ]
                if any(cells):
                    rows.append(cells)
    return _prepare_matrix_rows(rows)


def _rows_from_pdf_text(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in _normalize_dash_chars(text).splitlines():
        line = line.strip()
        if not line:
            continue
        parsed = _parse_pdf_text_line(line)
        if parsed:
            rows.append(parsed)
            continue
        parts = [p.strip() for p in re.split(r"\s{2,}", line) if p.strip()]
        if len(parts) >= 3:
            # Se a linha tem valor+saldo em colunas separadas, descarta o saldo (última col. monetária)
            money_idxs = [
                i for i, p in enumerate(parts) if _try_parse_amount_cents(p) is not None
            ]
            if len(money_idxs) >= 2:
                saldo_idx = money_idxs[-1]
                parts = [p for i, p in enumerate(parts) if i != saldo_idx]
            rows.append(parts)
    return _prepare_matrix_rows(rows)


def parse_pdf(content: bytes | bytearray) -> list[OfxTxn]:
    """Extrai lançamentos de PDF com texto (não escaneado).

    Tenta tabelas detectadas pelo pdfplumber e, em seguida, linhas
    no padrão data + descrição + valor. PDFs só com imagem não são suportados.
    """
    raw = bytes(content)
    if not raw:
        raise ValueError("Arquivo PDF vazio.")
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover
        raise ValueError("Suporte a PDF indisponível neste servidor.") from exc

    try:
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            table_rows = _rows_from_pdf_tables(pdf)
            text_chunks: list[str] = []
            for page in pdf.pages:
                extracted = page.extract_text() or ""
                if extracted.strip():
                    text_chunks.append(extracted)
            text = "\n".join(text_chunks)
    except Exception as exc:
        raise ValueError(
            "Não foi possível ler o PDF. "
            "Verifique se o arquivo não está corrompido ou protegido por senha."
        ) from exc

    errors: list[str] = []
    if table_rows:
        try:
            return _txns_from_tabular_rows(
                table_rows, source_label="PDF", fitid_prefix="PDF"
            )
        except ValueError as exc:
            errors.append(str(exc))

    line_rows = _rows_from_pdf_text(text)
    if line_rows:
        try:
            return _txns_from_tabular_rows(
                line_rows, source_label="PDF", fitid_prefix="PDF"
            )
        except ValueError as exc:
            errors.append(str(exc))

    # Alguns bancos embutem CSV/texto delimitado no PDF
    if text and (";" in text or "," in text or "\t" in text):
        try:
            txns = parse_csv(text)
            # Reetiqueta fitids sintéticos
            return [
                OfxTxn(
                    fitid=(
                        t.fitid.replace("CSV-", "PDF-", 1)
                        if t.fitid.startswith("CSV-")
                        else t.fitid
                    ),
                    posted_date=t.posted_date,
                    amount_cents=t.amount_cents,
                    direction=t.direction,
                    memo=t.memo,
                    trntype=t.trntype,
                )
                for t in txns
            ]
        except ValueError as exc:
            errors.append(str(exc))

    detail = f" ({errors[0]})" if errors else ""
    raise ValueError(
        "Nenhuma transação encontrada no PDF"
        f"{detail}. "
        "Use PDF com texto selecionável; extratos escaneados (imagem) não são suportados. "
        "Se o banco oferecer, prefira OFX ou CSV."
    )


def parse_statement(
    content: str | bytes,
    *,
    filename: str | None = None,
) -> list[OfxTxn]:
    """Detecta OFX/QFX, CSV/Flash ou PDF e devolve a mesma estrutura interna."""
    fmt = detect_statement_format(filename, content)
    if fmt == "csv":
        text = _decode_text(content)
        if _is_flash_statement(filename, text):
            return parse_flash_csv(content)
        return parse_csv(content)
    if fmt == "pdf":
        if isinstance(content, str):
            raise ValueError("PDF deve ser enviado como arquivo binário.")
        return parse_pdf(content)
    return parse_ofx(content)
