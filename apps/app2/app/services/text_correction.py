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


_PAYMENT_SOURCE_TAIL_RE = re.compile(
    r"\s+(?:na|no|nas|nos|da|do|das|dos|com|pela|pelo|via|usando)\s+"
    r"(?:a\s+|o\s+|minha\s+|meu\s+|uma\s+|um\s+)?"
    r"(?:conta(?:\s+banc[aá]ria)?|cart[aã]o(?:\s+de\s+cr[eé]dito)?|carteira)\b.*$",
    re.IGNORECASE,
)

_LEADING_COMMAND_RE = re.compile(
    r"^(?:eu\s+)*"
    r"(?:"
    r"fiz|fa[cç]o|vou\s+(?:fazer|lan[cç]ar|registrar|cadastrar)|"
    r"gastei|paguei|comprei|recebi|ganhei|tive|custei|"
    r"lan[cç](?:ar|ei|ando)|cadastr(?:ar|ei|ando)|registr(?:ar|ei|ando)|"
    r"despesa(?:\s+de)?|receita(?:\s+de)?|custo(?:\s+de)?"
    r")\s+",
    re.IGNORECASE,
)

_LEADING_ARTICLE_RE = re.compile(
    r"^(?:uma|um|uns|umas|a|o|as|os|ao|à|aos|às|de|do|da|dos|das)\s+",
    re.IGNORECASE,
)

_GERUND_TO_NOUN = {
    "comprando": "compra",
    "pagando": "pagamento",
    "gastando": "gasto",
    "recebendo": "recebimento",
    "lançando": "lançamento",
    "lancando": "lançamento",
}


_PAYMENT_ONLY_DESCRIPTIONS = frozenset(
    {
        "cartão",
        "cartao",
        "conta",
        "carteira",
        "crédito",
        "credito",
        "débito",
        "debito",
        "no cartão",
        "no cartao",
        "na conta",
        "na carteira",
    }
)


def is_weak_movement_description(text: str | None) -> bool:
    if not text or not str(text).strip():
        return True
    normalized = re.sub(r"\s+", " ", str(text).strip().lower())
    if normalized in _PAYMENT_ONLY_DESCRIPTIONS:
        return True
    if normalized in {"lançamento", "lancamento"}:
        return True
    return False

def sanitize_movement_description(text: str) -> str:
    """Remove verbo de comando e conta/cartão da descrição do lançamento."""
    if not text or not text.strip():
        return text

    desc = re.sub(r"\s+", " ", text.strip())
    # Repete: "fiz uma despesa de ..."
    for _ in range(3):
        cleaned = _PAYMENT_SOURCE_TAIL_RE.sub("", desc).strip(" -,.")
        cleaned = _LEADING_COMMAND_RE.sub("", cleaned).strip(" -,.")
        cleaned = _LEADING_ARTICLE_RE.sub("", cleaned).strip(" -,.")
        if cleaned == desc:
            break
        desc = cleaned

    # Ruído de valor / parcelamento: "Carne de Boi o valor de", "blusa em 10 vezes"
    desc = re.sub(r"\s*\bo\s+valor\s+de\b\s*", " ", desc, flags=re.IGNORECASE)
    desc = re.sub(r"\s*\bvalor\s+de\b\s*$", "", desc, flags=re.IGNORECASE)
    desc = re.sub(r"\s*\bem\s+\d+\s*(?:x|vezes)\b", "", desc, flags=re.IGNORECASE)
    desc = re.sub(r"\s*\b\d+\s*(?:x|vezes)\b", "", desc, flags=re.IGNORECASE)
    desc = re.sub(r"\s*\bem\s+vezes\b", "", desc, flags=re.IGNORECASE)
    desc = re.sub(r"\s*\bparcelad[oa]s?\b", "", desc, flags=re.IGNORECASE)
    desc = re.sub(r"\s+", " ", desc).strip(" -,.")

    parts = desc.split(None, 1)
    if parts:
        first_lower = parts[0].lower()
        if first_lower in _GERUND_TO_NOUN:
            noun = _GERUND_TO_NOUN[first_lower]
            rest = parts[1] if len(parts) > 1 else ""
            # "compra carne" → "compra de carne" quando falta a preposição
            if rest and not re.match(
                r"^(?:de|do|da|dos|das|no|na|em|com|para)\b",
                rest,
                re.IGNORECASE,
            ):
                desc = f"{noun} de {rest}".strip()
            else:
                desc = f"{noun} {rest}".strip()

    desc = re.sub(r"\s+", " ", desc).strip(" -,.")
    if is_weak_movement_description(desc):
        return ""
    return desc or text.strip()


def _spell_and_capitalize(text: str) -> str:
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


def correct_movement_description(text: str) -> str:
    """Remove ruído de comando, corrige ortografia e capitaliza."""
    if not text or not text.strip():
        return text
    sanitized = sanitize_movement_description(text)
    if not sanitized:
        return ""
    return _spell_and_capitalize(sanitized)


def correct_category_name(text: str) -> str:
    """Normaliza nome de categoria com ortografia e primeira letra maiúscula."""
    return _spell_and_capitalize(text)
