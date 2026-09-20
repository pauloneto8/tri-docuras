from __future__ import annotations

import difflib
import unicodedata

DEFAULT_CUTOFF = 0.78


def _normalize(text: str) -> str:
    stripped = unicodedata.normalize("NFKD", text.strip().lower())
    return "".join(c for c in stripped if not unicodedata.combining(c))


def fuzzy_find_one(query: str, candidates: list[str], cutoff: float = DEFAULT_CUTOFF) -> str | None:
    """Retorna o candidato mais parecido com `query`, ou None se nenhum passar do cutoff.

    Usado só depois que uma correspondência exata/substring falha, para tolerar erro de
    digitação ou acento faltante em nomes já cadastrados pelo usuário (conta, cartão,
    categoria). A comparação ignora acentos (ex.: "Itau" casa com "Itaú") — igual ao
    tratamento já usado em text_correction.py.
    """
    if not query or not candidates:
        return None
    normalized_query = _normalize(query)
    if not normalized_query:
        return None
    normalized_map = {_normalize(candidate): candidate for candidate in candidates}
    matches = difflib.get_close_matches(
        normalized_query, list(normalized_map.keys()), n=1, cutoff=cutoff
    )
    return normalized_map[matches[0]] if matches else None
