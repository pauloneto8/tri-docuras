"""Detecta se a mensagem preenche apenas o slot atual do wizard."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.tools import parse_amount
from app.services.transaction_slots import (
    list_active_account_names,
    list_category_names,
    parse_account_answer,
    parse_category_answer,
)

CORRECTION_HINTS = (
    "corrija",
    "corrigir",
    "correção",
    "correcao",
    "editar",
    "edite",
    "alterar",
    "altere",
    "mudar",
    "mude",
    "trocar",
    "troque",
    "atualizar",
    "atualize",
    "lançamento",
    "lancamento",
    "transação",
    "transacao",
    "despesa com",
    "receita com",
)

MAX_SLOT_WORDS = 12


def is_complex_message(message: str) -> bool:
    lower = message.lower().strip()
    if any(hint in lower for hint in CORRECTION_HINTS):
        return True
    return len(lower.split()) > MAX_SLOT_WORDS


def is_short_slot_message(message: str, *, max_words: int = MAX_SLOT_WORDS) -> bool:
    text = message.strip()
    if not text or is_complex_message(text):
        return False
    return len(text.split()) <= max_words
