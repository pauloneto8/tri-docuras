"""Loop agêntico v2 (Groq + ferramentas, confirmação em lote).

O cérebro só raciocina e chama ferramentas. Cálculos continuam em Python
(`finance.py`); leituras rodam na hora, escritas ficam pendentes de confirmação
e são executadas por `confirm.py`. `llm` é injetável para os testes usarem um
falso roteirizado, sem chave Groq.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from app.agent.groq import chat_with_tools
from app.agent.prompt_v2 import build_system_prompt
from app.agent.toolkit import (
    ToolSpec,
    build_toolkit,
    openai_tools,
    run_read,
    validate_write,
)
from app.config import settings
from app.schemas import ToolCall
from app.services.tools import format_pending_confirmation

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 8
MAX_TOOL_CONTENT_CHARS = 6000
_MONEY_RE = re.compile(r"R\$\s?-?\d{1,3}(?:\.\d{3})*,\d{2}")

_FALLBACK_MONEY = (
    "Consegui olhar seus dados, mas prefiro não arriscar mostrar um número que "
    "não bateu. Pode reformular a pergunta de um jeito mais específico?"
)


class BrainResult:
    def __init__(
        self,
        response: str = "",
        pending_plan: Optional[Dict[str, Any]] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        metrics: Optional[Dict[str, Any]] = None,
    ):
        self.response = response
        self.pending_plan = pending_plan or {}
        self.tool_calls = tool_calls or []
        self.metrics = metrics or {}

    @property
    def needs_confirmation(self) -> bool:
        return bool(self.pending_plan.get("actions"))


def _json_default(obj: Any) -> str:
    return str(obj)


def _tool_message(tool_call_id: str, result: Any) -> dict:
    content = json.dumps(result, ensure_ascii=False, default=_json_default)
    if len(content) > MAX_TOOL_CONTENT_CHARS:
        content = content[:MAX_TOOL_CONTENT_CHARS] + "…(truncado)"
    return {"role": "tool", "tool_call_id": tool_call_id, "content": content}


def _extract_arguments(raw: Any) -> tuple[dict, Optional[str]]:
    if isinstance(raw, dict):
        return raw, None
    if raw in (None, ""):
        return {}, None
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError) as exc:
        return {}, f"JSON inválido nos argumentos: {exc}"
    if not isinstance(parsed, dict):
        return {}, "Os argumentos devem ser um objeto JSON."
    return parsed, None


def _preview_action(spec: ToolSpec, arguments: dict) -> str:
    try:
        return format_pending_confirmation(ToolCall(tool=spec.name, arguments=arguments))
    except Exception:  # noqa: BLE001 — preview é cosmético, não deve derrubar o loop
        return f"Ação pendente: {spec.name}"


def _safe_summary(fetch, render) -> Optional[str]:
    """Monta um bloco do prompt; contexto ausente não pode derrubar o loop."""
    try:
        return "\n".join(render(item) for item in fetch()) or None
    except Exception:  # noqa: BLE001 — o contexto do prompt é melhor-esforço
        logger.warning("Falha ao montar contexto do prompt", exc_info=True)
        return None


def _context_summaries(db, user_id: int) -> dict:
    """Contas, cartões e categorias do usuário para o prompt (sem cálculo no LLM)."""
    from app.services import finance
    from app.services.credit_cards import list_credit_cards

    def render_account(acc: dict) -> str:
        return (
            f"- id={acc['id']} {acc['account']} ({acc['account_type_label']}), "
            f"saldo_atual=R$ {acc['balance']}"
        )

    def render_card(card: dict) -> str:
        return (
            f"- id={card['id']} {card['name']}"
            + (f", instituição={card['institution']}" if card.get("institution") else "")
            + f", fechamento={card['closing_day']}, vencimento={card['due_day']}"
            + (
                f", liquidação={card['settlement_account_name']}"
                if card.get("settlement_account_name")
                else ""
            )
        )

    def render_category(cat: dict) -> str:
        return (
            f"- id={cat['id']} {cat['name']} ({cat['type_label']})"
            + (f", keywords={cat['keywords']}" if cat.get("keywords") else "")
        )

    return {
        "accounts_summary": _safe_summary(
            lambda: finance.account_balances(db, user_id), render_account
        ),
        "cards_summary": _safe_summary(lambda: list_credit_cards(db, user_id), render_card),
        "categories_summary": _safe_summary(
            lambda: finance.list_user_categories(db, user_id), render_category
        ),
    }


async def run(
    *,
    db,
    user_id: int,
    message: str,
    channel: str = "web",
    history: Optional[List[Dict[str, Any]]] = None,
    llm: Optional[Any] = None,
    max_iterations: int = MAX_ITERATIONS,
) -> BrainResult:
    start = time.perf_counter()
    toolkit = build_toolkit()
    tools = openai_tools(toolkit)
    call_llm = llm or chat_with_tools

    system = build_system_prompt(user_id=user_id, channel=channel, **_context_summaries(db, user_id))
    messages: List[Dict[str, Any]] = [{"role": "system", "content": system}]
    known_money: set[str] = set()
    for item in history or []:
        if isinstance(item, dict) and item.get("role") in {"user", "assistant"}:
            messages.append({"role": item["role"], "content": item.get("content", "")})
            if item.get("role") == "assistant":
                known_money.update(_MONEY_RE.findall(item.get("content", "") or ""))
    messages.append({"role": "user", "content": message})

    pending: List[Dict[str, Any]] = []
    tool_calls_log: List[Dict[str, Any]] = []
    seen: Dict[tuple, Any] = {}
    tokens = {"prompt": 0, "completion": 0, "cached": 0}

    iterations = 0
    final_text = ""
    for iterations in range(1, max_iterations + 1):
        reply = await call_llm(messages, tools)
        _accumulate_tokens(tokens, reply)
        content = (reply or {}).get("content") or ""
        tool_calls = (reply or {}).get("tool_calls") or []

        if not tool_calls:
            final_text = content
            unknown = [m for m in _MONEY_RE.findall(final_text) if m not in known_money]
            if unknown:
                messages.append({"role": "assistant", "content": content})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Reescreva a resposta usando SOMENTE valores que as "
                            "ferramentas devolveram, sem inventar números."
                        ),
                    }
                )
                retry = await call_llm(messages, tools)
                _accumulate_tokens(tokens, retry)
                retry_text = (retry or {}).get("content") or ""
                retry_unknown = [
                    m for m in _MONEY_RE.findall(retry_text) if m not in known_money
                ]
                if retry_unknown or not retry_text:
                    return BrainResult(
                        response=_FALLBACK_MONEY,
                        tool_calls=tool_calls_log,
                        metrics=_metrics(start, iterations, tool_calls_log, tokens),
                    )
                final_text = retry_text
            break

        messages.append(
            {"role": "assistant", "content": content, "tool_calls": tool_calls}
        )
        for tc in tool_calls:
            fn = (tc or {}).get("function") or {}
            name = fn.get("name") or ""
            tool_call_id = tc.get("id") or name
            arguments, parse_error = _extract_arguments(fn.get("arguments"))
            tool_calls_log.append({"tool": name, "arguments": arguments})

            spec = toolkit.get(name)
            if spec is None:
                result: Any = {"error": f"Ferramenta desconhecida: {name}"}
                messages.append(_tool_message(tool_call_id, result))
                continue

            key = (name, json.dumps(arguments, sort_keys=True, default=str))
            if key in seen:
                messages.append(_tool_message(tool_call_id, seen[key]))
                continue

            if parse_error:
                result = {"error": parse_error, "hint": "Envie os argumentos novamente em JSON válido."}
            elif spec.kind == "read":
                try:
                    result = run_read(spec, db, user_id, arguments)
                except Exception as exc:  # noqa: BLE001 — erro vira resultado da tool
                    logger.warning("Erro na ferramenta de leitura %s: %s", name, exc)
                    result = {"error": str(exc), "hint": "Ajuste os parâmetros e tente de novo."}
                else:
                    known_money.update(
                        _MONEY_RE.findall(
                            json.dumps(result, ensure_ascii=False, default=_json_default)
                        )
                    )
            else:
                try:
                    validated = validate_write(spec, arguments)
                except ValidationError as exc:
                    result = {
                        "error": "Argumentos inválidos.",
                        "details": exc.errors(),
                        "hint": "Corrija os campos e tente de novo.",
                    }
                else:
                    preview = _preview_action(spec, validated)
                    pending.append({"tool": name, "arguments": validated})
                    result = {"status": "pending_confirmation", "preview": preview}
                    known_money.update(_MONEY_RE.findall(preview))

            seen[key] = result
            messages.append(_tool_message(tool_call_id, result))
    else:
        final_text = ""

    if not final_text:
        if pending:
            previews = [
                _preview_action(toolkit[a["tool"]], a["arguments"])
                for a in pending
                if a["tool"] in toolkit
            ]
            final_text = "\n\n".join(previews)
        else:
            final_text = (
                "Não consegui concluir esse pedido. Pode reformular de um jeito "
                "mais específico?"
            )

    plan: Dict[str, Any] = {}
    if pending:
        plan = {
            "actions": pending,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    return BrainResult(
        response=final_text,
        pending_plan=plan,
        tool_calls=tool_calls_log,
        metrics=_metrics(start, iterations, tool_calls_log, tokens),
    )


def _metrics(
    start: float,
    iterations: int,
    tool_calls: List[Dict[str, Any]],
    tokens: Dict[str, int],
) -> Dict[str, Any]:
    return {
        "iterations": iterations,
        "tools": [c["tool"] for c in tool_calls],
        "tool_count": len(tool_calls),
        "latency_ms": int((time.perf_counter() - start) * 1000),
        "model": getattr(settings, "groq_model", None),
        "tokens": {
            "prompt": tokens.get("prompt", 0),
            "completion": tokens.get("completion", 0),
            "cached": tokens.get("cached", 0),
            "total": tokens.get("prompt", 0) + tokens.get("completion", 0),
        },
    }


def _accumulate_tokens(tokens: Dict[str, int], reply: Optional[Dict[str, Any]]) -> None:
    """Soma o `usage` de cada chamada do loop.

    O `cached` vem em `prompt_tokens_details.cached_tokens` (o Groq só o
    manda em alguns planos); o free tier conta tokens em cache como não
    consumidos no orçamento diário, então saber quanto do prompt é cache diz
    quanto custa de verdade uma mensagem.
    """
    usage = (reply or {}).get("usage") or {}
    if not isinstance(usage, dict):
        return
    tokens["prompt"] += int(usage.get("prompt_tokens") or 0)
    tokens["completion"] += int(usage.get("completion_tokens") or 0)
    details = usage.get("prompt_tokens_details") or {}
    if isinstance(details, dict):
        tokens["cached"] += int(details.get("cached_tokens") or 0)
