"""Extrai vários lançamentos (despesas/receitas) de uma única mensagem."""

from __future__ import annotations

import re
from dataclasses import dataclass
from re import Match

from app.services.text_correction import correct_movement_description
from app.services.tools import (
    AMOUNT_RE,
    EXPENSE_HINTS,
    INCOME_HINTS,
    parse_amount,
    parse_date,
)

PENDING_MOVEMENTS_KEY = "pending_movements"

TRAILING_CONNECTOR_RE = re.compile(r"\s+(?:e|e\s+tamb[eé]m|e\s+ainda|e\s+mais)\s*$", re.IGNORECASE)
LEADING_NOISE_RE = re.compile(
    r"^(?:r\$\s*)?(?:de|com|em|para|no|na|nos|nas)\s+",
    re.IGNORECASE,
)
SEGMENT_BOUNDARY_RE = re.compile(
    r"(?:\.\s*|\s+e\s+tamb[eé]m\s+|\s+e\s+ainda\s+|\s+e\s+mais\s+|\s+e\s+)",
    re.IGNORECASE,
)


@dataclass
class ParsedMovement:
    amount: str
    description: str
    tx_type: str  # expense | income
    transaction_date: str | None = None
    account_name: str | None = None
    category_name: str | None = None

    def to_dict(self) -> dict:
        return {
            "amount": self.amount,
            "description": self.description,
            "tx_type": self.tx_type,
            "transaction_date": self.transaction_date,
            "account_name": self.account_name,
            "category_name": self.category_name,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ParsedMovement:
        return cls(
            amount=data["amount"],
            description=data["description"],
            tx_type=data["tx_type"],
            transaction_date=data.get("transaction_date"),
            account_name=data.get("account_name"),
            category_name=data.get("category_name"),
        )


def count_amounts(message: str) -> int:
    return len(list(AMOUNT_RE.finditer(message)))


def _normalize_amount_raw(raw: str) -> str | None:
    normalized = raw
    if "," in normalized and "." in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    else:
        normalized = normalized.replace(",", ".")
    if parse_amount(normalized) is None and parse_amount(raw) is None:
        return None
    return parse_amount(raw) or parse_amount(normalized)


def _detect_tx_type(message: str) -> str | None:
    lower = message.lower()
    has_expense = any(h in lower for h in EXPENSE_HINTS) or "despesa" in lower
    has_income = any(h in lower for h in INCOME_HINTS) or "receita" in lower
    if has_expense and not has_income:
        return "expense"
    if has_income and not has_expense:
        return "income"
    if has_expense:
        return "expense"
    return None


def _resolve_tx_type(message: str, tx_type_hint: str | None) -> str | None:
    if tx_type_hint in {"expense", "income"}:
        return tx_type_hint
    return _detect_tx_type(message)


def _description_after_amount(text: str, match: Match[str], span_end: int) -> str:
    tail = text[match.end() : span_end].strip()
    parts = SEGMENT_BOUNDARY_RE.split(tail, maxsplit=1)
    tail = parts[0].strip(" -,.")
    tail = TRAILING_CONNECTOR_RE.sub("", tail).strip(" -,.")
    tail = LEADING_NOISE_RE.sub("", tail).strip()
    for token in (
        *EXPENSE_HINTS,
        *INCOME_HINTS,
        "eu",
        "ontem",
        "hoje",
        "tive",
        "tivemos",
    ):
        tail = re.sub(rf"\b{re.escape(token)}\b", "", tail, flags=re.IGNORECASE)
    tail = re.sub(r"\s+", " ", tail).strip(" -,.")
    if not tail:
        return "Lançamento"
    return correct_movement_description(tail) or "Lançamento"


def _movement_from_match(
    text: str,
    match: Match[str],
    span_end: int,
    tx_type: str,
    tx_date: str | None,
) -> ParsedMovement | None:
    amount = _normalize_amount_raw(match.group(1))
    if not amount:
        return None
    description = _description_after_amount(text, match, span_end)
    return ParsedMovement(
        amount=amount,
        description=description,
        tx_type=tx_type,
        transaction_date=tx_date,
    )


def parse_multi_movements(
    message: str,
    *,
    tx_type_hint: str | None = None,
) -> list[ParsedMovement] | None:
    """Retorna 2+ lançamentos se a mensagem contiver múltiplos valores monetários."""
    text = message.strip()
    if not text:
        return None

    amounts_found = list(AMOUNT_RE.finditer(text))
    if len(amounts_found) < 2:
        return None

    tx_type = _resolve_tx_type(text, tx_type_hint)
    if not tx_type:
        return None

    tx_date = None
    parsed_date = parse_date(text)
    if parsed_date:
        tx_date = parsed_date.isoformat()

    movements: list[ParsedMovement] = []
    for i, match in enumerate(amounts_found):
        span_end = amounts_found[i + 1].start() if i + 1 < len(amounts_found) else len(text)
        item = _movement_from_match(text, match, span_end, tx_type, tx_date)
        if item:
            movements.append(item)

    if len(movements) < 2:
        return None

    seen_amounts: set[str] = set()
    unique: list[ParsedMovement] = []
    for movement in movements:
        if movement.amount in seen_amounts:
            continue
        seen_amounts.add(movement.amount)
        unique.append(movement)

    return unique if len(unique) >= 2 else None


def clear_pending_movements(session: dict) -> None:
    session.pop(PENDING_MOVEMENTS_KEY, None)


def get_pending_movements(session: dict) -> dict | None:
    return session.get(PENDING_MOVEMENTS_KEY)
