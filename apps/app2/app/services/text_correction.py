"""Correção ortográfica leve para descrições de lançamentos (pt-BR)."""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

from spellchecker import SpellChecker

# Nomes próprios e termos que o dicionário não cobre bem.
MANUAL_FIXES: dict[str, str] = {
    "timbauba": "Timbaúba",
    "timbaúba": "Timbaúba",
    "nubank": "Nubank",
    "itau": "Itaú",
    "itaú": "Itaú",
    "bradesco": "Bradesco",
    "santander": "Santander",
    "caixa": "Caixa",
    "inter": "Inter",
    "picpay": "PicPay",
    "mercado pago": "Mercado Pago",
}

TOKEN_RE = re.compile(r"^(\W*)([\wÀ-ÿ]+)(\W*)$", re.UNICODE)


@lru_cache(maxsize=1)
def _spellchecker() -> SpellChecker:
    return SpellChecker(language="pt")


def _apply_case(original: str, fixed: str) -> str:
    if not fixed:
        return fixed
    if original.isupper():
        return fixed.upper()
    if original[0].isupper() and (len(original) == 1 or original[1:].islower()):
        return fixed[0].upper() + fixed[1:] if fixed else fixed
    return fixed.lower()


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def _is_accent_only_fix(original: str, suggestion: str) -> bool:
    return _strip_accents(suggestion.lower()) == original.lower()


def _correct_word_core(core: str) -> str:
    if not core:
        return core

    lower = core.lower()
    if lower in MANUAL_FIXES:
        return _apply_case(core, MANUAL_FIXES[lower])

    spell = _spellchecker()
    if lower in spell:
        return core

    suggestion = spell.correction(lower)
    if not suggestion or suggestion == lower:
        return core
    if not _is_accent_only_fix(lower, suggestion):
        return core
    return _apply_case(core, suggestion)


def _correct_token(token: str) -> str:
    match = TOKEN_RE.match(token)
    if not match:
        return token
    prefix, core, suffix = match.groups()
    if not core:
        return token
    return f"{prefix}{_correct_word_core(core)}{suffix}"


def correct_movement_description(text: str) -> str:
    """Normaliza espaços, corrige ortografia e capitaliza a primeira letra."""
    if not text or not text.strip():
        return text

    normalized = re.sub(r"\s+", " ", text.strip())
    lower_full = normalized.lower()
    if lower_full in MANUAL_FIXES:
        return MANUAL_FIXES[lower_full]

    tokens = normalized.split(" ")
    corrected = [_correct_token(token) for token in tokens]
    result = " ".join(corrected)
    return result[0].upper() + result[1:] if result else result


def correct_category_name(text: str) -> str:
    """Normaliza nome de categoria com ortografia e primeira letra maiúscula."""
    return correct_movement_description(text)
