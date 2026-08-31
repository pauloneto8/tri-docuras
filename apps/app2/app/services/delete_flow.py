"""Fluxo de exclusão com desambiguação e confirmação obrigatória."""

from __future__ import annotations

import re

from app.schemas import AgentResponse, DeleteTransactionInput, ListTransactionsInput, ToolCall, decimal_to_cents
from app.services import finance
from app.services.tools import format_pending_confirmation, parse_amount

PENDING_DELETE_KEY = "pending_delete"
CANCEL_WORDS = {"cancelar", "desistir", "abortar", "sair", "não", "nao"}
MAX_CANDIDATES = 5


def get_pending_delete(session: dict) -> dict | None:
    return session.get(PENDING_DELETE_KEY)


def clear_pending_delete(session: dict) -> None:
    session.pop(PENDING_DELETE_KEY, None)


def _format_candidate_line(item: dict) -> str:
    return (
        f"- id {item['id']}: {item['type']} R$ {item['amount']} — "
        f"'{item['description']}' — conta {item['account']} ({item['transaction_date']})"
    )


def _format_candidates_message(candidates: list[dict], *, intro: str) -> str:
    lines = [_format_candidate_line(item) for item in candidates]
    return (
        f"{intro}\n"
        + "\n".join(lines)
        + "\n\nInforme o **id**, o valor ou a descrição do lançamento que deseja excluir."
    )


def _set_pending_delete(session: dict, candidates: list[dict]) -> None:
    session[PENDING_DELETE_KEY] = {
        "candidates": candidates,
    }


def _unique_candidates(candidates: list[dict]) -> list[dict]:
    seen: set[int] = set()
    unique: list[dict] = []
    for item in candidates:
        tx_id = item["id"]
        if tx_id in seen:
            continue
        seen.add(tx_id)
        unique.append(item)
    return unique


def _load_candidates_by_ids(
    db, user_id: int, candidate_ids: list[int]
) -> list[dict]:
    results: list[dict] = []
    for tx_id in candidate_ids:
        tx = finance.find_transaction(db, user_id, transaction_id=tx_id)
        if tx:
            results.append(finance.format_transaction(tx))
    return results


def _search_candidates(
    db,
    user_id: int,
    *,
    transaction_id: int | None = None,
    description: str | None = None,
    amount: str | None = None,
) -> list[dict]:
    if transaction_id is not None:
        tx = finance.find_transaction(db, user_id, transaction_id=transaction_id)
        return [finance.format_transaction(tx)] if tx else []

    lookup_description = description if description else None
    txs = finance.find_transactions(
        db,
        user_id,
        description=lookup_description,
        amount=amount,
        limit=MAX_CANDIDATES,
    )
    return [finance.format_transaction(tx) for tx in txs]


def _recent_candidates(db, user_id: int) -> list[dict]:
    return finance.list_transactions(
        db, user_id, ListTransactionsInput(limit=MAX_CANDIDATES, type="all")
    )


def _confirmation_tool_call(preview: dict) -> ToolCall:
    return ToolCall(
        tool="delete_transaction",
        arguments={
            "transaction_id": preview["id"],
            "_preview": preview,
        },
    )


def _confirmation_response(preview: dict, *, source: str = "delete_flow") -> AgentResponse:
    tool_call = _confirmation_tool_call(preview)
    return AgentResponse(
        message=format_pending_confirmation(tool_call),
        needs_confirmation=True,
        pending_action=tool_call.model_dump(),
        tool_used="delete_transaction",
        source=source,
    )


def _parse_transaction_id(message: str) -> int | None:
    text = message.strip().lower()
    match = re.search(r"\b(?:id\s*)?(\d+)\b", text)
    if match:
        return int(match.group(1))
    return None


def _filter_candidates_by_message(
    candidates: list[dict], message: str
) -> list[dict]:
    text = message.strip()
    lower = text.lower()

    if lower in {"o primeiro", "a primeira", "primeiro", "primeira"}:
        return candidates[:1] if candidates else []

    if lower in {"o último", "o ultimo", "a última", "a ultima", "último", "ultimo"}:
        return candidates[-1:] if candidates else []

    tx_id = _parse_transaction_id(message)
    if tx_id is not None:
        return [c for c in candidates if c["id"] == tx_id]

    amount = parse_amount(message)
    if amount:
        matched = [
            c
            for c in candidates
            if decimal_to_cents(c["amount"]) == decimal_to_cents(amount)
        ]
        if matched:
            return matched

    if len(text) >= 2:
        matched = [
            c
            for c in candidates
            if lower in c["description"].lower()
            or c["description"].lower() in lower
        ]
        if matched:
            return matched

    return []


def _is_delete_choice_message(message: str) -> bool:
    lower = message.strip().lower()
    if lower in CANCEL_WORDS:
        return True
    if _parse_transaction_id(message) is not None:
        return True
    if parse_amount(message):
        return True
    if lower in {
        "o primeiro",
        "a primeira",
        "primeiro",
        "primeira",
        "o último",
        "o ultimo",
        "a última",
        "a ultima",
        "último",
        "ultimo",
    }:
        return True
    if len(message.strip()) >= 2 and len(message.split()) <= 8:
        return True
    return False


def prepare_delete_transaction(
    db,
    user_id: int,
    tool_call: ToolCall,
    session: dict,
) -> tuple[ToolCall | None, str | None]:
    """Resolve exclusão: só confirma com alvo único; na dúvida, pergunta."""
    args = dict(tool_call.arguments)
    clean_args = {k: v for k, v in args.items() if not str(k).startswith("_")}
    payload = DeleteTransactionInput(**clean_args)

    has_criteria = any(
        [payload.transaction_id, payload.amount, payload.description]
    )

    if not has_criteria:
        candidates = _recent_candidates(db, user_id)
        if not candidates:
            clear_pending_delete(session)
            return None, "Nenhum lançamento encontrado para excluir."
        _set_pending_delete(session, candidates)
        return None, _format_candidates_message(
            candidates,
            intro="Qual lançamento deseja excluir? Estes são os mais recentes:",
        )

    candidates = _unique_candidates(
        _search_candidates(
            db,
            user_id,
            transaction_id=payload.transaction_id,
            description=payload.description,
            amount=payload.amount,
        )
    )

    if not candidates:
        clear_pending_delete(session)
        return None, "Lançamento não encontrado. Verifique o valor, a descrição ou o id."

    if len(candidates) == 1:
        clear_pending_delete(session)
        return _confirmation_tool_call(candidates[0]), None

    _set_pending_delete(session, candidates)
    return None, _format_candidates_message(
        candidates,
        intro="Encontrei mais de um lançamento. Qual deles deseja excluir?",
    )


def try_process_pending_delete(
    session: dict,
    message: str,
    db,
    user_id: int,
) -> AgentResponse | None:
    pending = get_pending_delete(session)
    if not pending:
        return None

    if message.strip().lower() in CANCEL_WORDS:
        clear_pending_delete(session)
        return AgentResponse(
            message="Exclusão cancelada.",
            source="delete_flow",
        )

    candidates = pending.get("candidates") or []
    if not candidates:
        clear_pending_delete(session)
        return None

    if not _is_delete_choice_message(message):
        clear_pending_delete(session)
        return None

    matched = _filter_candidates_by_message(candidates, message)

    if len(matched) == 1:
        clear_pending_delete(session)
        return _confirmation_response(matched[0])

    if len(matched) > 1:
        _set_pending_delete(session, matched)
        return AgentResponse(
            message=_format_candidates_message(
                matched,
                intro="Ainda há mais de um lançamento com esse critério. Qual deles excluir?",
            ),
            source="delete_flow",
        )

    return AgentResponse(
        message=_format_candidates_message(
            candidates,
            intro="Não identifiquei qual lançamento você quer excluir. Escolha um da lista:",
        ),
        source="delete_flow",
    )
