"""Parse de extratos OFX/QFX e CSV para a mesma estrutura interna."""

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
}
_CSV_DEBIT_ALIASES = {"debito", "débito", "debit", "saida", "saída", "despesa"}
_CSV_CREDIT_ALIASES = {"credito", "crédito", "credit", "entrada", "receita"}


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


def _try_parse_amount_cents(raw: str) -> int | None:
    text = (raw or "").strip()
    if not text:
        return None
    # Evita tratar datas DD/MM/YYYY como valor
    if _try_parse_date(text) is not None and re.fullmatch(r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}", text):
        return None
    cleaned = text.replace(" ", "").replace("R$", "").replace("r$", "")
    negative = cleaned.startswith("-") or cleaned.startswith("(")
    cleaned = cleaned.lstrip("+-").strip("()")
    if not cleaned or not re.search(r"\d", cleaned):
        return None
    # Só dígitos + separadores decimais/milhar
    if not re.fullmatch(r"[\d.,]+", cleaned):
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
    if cents == 0 and not negative and value == 0:
        return 0
    return -cents if negative or value < 0 else cents


def _parse_amount_to_cents(raw: str) -> int:
    parsed = _try_parse_amount_cents(raw)
    if parsed is None:
        raise ValueError(f"Valor vazio ou inválido: {raw!r}")
    return parsed


def _direction_from_amount_and_type(signed_cents: int, trntype: str) -> Direction:
    t = _strip_accents(trntype or "").upper()
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
    }
    if t in credit_types and signed_cents >= 0:
        return "credit"
    if t in debit_types and signed_cents <= 0:
        return "debit"
    if t in credit_types:
        return "credit"
    if t in debit_types:
        return "debit"
    if signed_cents < 0:
        return "debit"
    if signed_cents > 0:
        return "credit"
    return "debit"


def _synthetic_fitid(posted: date, amount_cents: int, memo: str, index: int) -> str:
    raw = f"{posted.isoformat()}|{amount_cents}|{normalize_memo(memo)}|{index}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]
    return f"CSV-{digest}"


def detect_statement_format(
    filename: str | None, content: str | bytes
) -> Literal["ofx", "csv"]:
    name = (filename or "").lower()
    suffix = Path(name).suffix
    if suffix in {".csv", ".txt"}:
        return "csv"
    if suffix in {".ofx", ".qfx"}:
        return "ofx"
    text = _decode_text(content)[:4000].upper()
    if "<OFX" in text or "<STMTTRN" in text or "OFXHEADER" in text:
        return "ofx"
    if "," in text or ";" in text or "\t" in text:
        return "csv"
    raise ValueError("Formato não reconhecido. Envie um arquivo OFX/QFX ou CSV.")


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
    """Detecta delimitador priorizando `;` (CSV BR com vírgula decimal)."""
    lines = [ln for ln in sample.splitlines() if ln.strip()][:8]
    if not lines:
        return ","
    semi = sum(ln.count(";") for ln in lines)
    tabs = sum(ln.count("\t") for ln in lines)
    pipes = sum(ln.count("|") for ln in lines)
    commas = sum(ln.count(",") for ln in lines)
    # Ponto e vírgula é o padrão brasileiro de extrato
    if semi > 0 and semi >= max(tabs, pipes):
        return ";"
    if tabs > 0 and tabs >= max(commas, pipes):
        return "\t"
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

    best_i = 0
    best_score = -1.0
    window = 5
    for i in range(len(rows)):
        chunk = rows[i : i + window]
        if not chunk:
            continue
        # Não começar no meio se a linha anterior parece cabeçalho
        if i > 0 and _looks_like_header_row(rows[i - 1]):
            continue
        score = sum(_row_data_score(r) for r in chunk) / len(chunk)
        widths = {len(r) for r in chunk if len(r) >= 2}
        if len(widths) == 1:
            score += 1.0
        if score > best_score:
            best_score = score
            best_i = i
    return best_i


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
        if len(values) >= 2 and all(v < 0 for v in values):
            debit_scores[i] += 1.0
        # Coluna de valor “mista” (sinais diferentes) é melhor como amount único
        if len(values) >= 2 and any(v > 0 for v in values) and any(v < 0 for v in values):
            amount_scores[i] += 2.0

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

    start = _find_table_start(rows)
    table = rows[start:]
    if not table:
        raise ValueError("Não encontrei a tabela de movimentos no arquivo.")

    header: list[str] | None = None
    data_rows = table
    if _looks_like_header_row(table[0]):
        header = table[0]
        data_rows = table[1:]
    if not data_rows:
        raise ValueError("CSV só tem cabeçalho, sem lançamentos.")

    # Homogeneizar largura pela moda das larguras das linhas de dados
    widths = [len(r) for r in data_rows if len(r) >= 2]
    if not widths:
        raise ValueError("Linhas do CSV não têm colunas suficientes.")
    target_width = max(set(widths), key=widths.count)
    data_rows = [r for r in data_rows if len(r) >= max(2, target_width - 1)]
    if not data_rows:
        raise ValueError("Não encontrei linhas de movimento utilizáveis no CSV.")

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
            # Linha de total/rodapé — ignora
            continue
        memo = (memo or "Movimento CSV")[:255]

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

        if signed == 0:
            continue
        direction = _direction_from_amount_and_type(signed, trntype)
        amount_cents = abs(signed)
        raw_fitid = _cell(row, layout.fitid_idx)
        fitid = (raw_fitid or _synthetic_fitid(posted, amount_cents, memo, index))[:128]
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
            "Nenhuma transação encontrada no arquivo CSV. "
            "Confira se há linhas com data e valor."
        )
    return txns


def parse_statement(
    content: str | bytes,
    *,
    filename: str | None = None,
) -> list[OfxTxn]:
    """Detecta OFX/QFX ou CSV e devolve a mesma estrutura interna."""
    fmt = detect_statement_format(filename, content)
    if fmt == "csv":
        return parse_csv(content)
    return parse_ofx(content)
