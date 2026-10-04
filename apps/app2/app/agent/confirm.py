"""Confirmação em lote (plano pendente)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from app.schemas import ToolCall
from app.services.tools import execute_tool, format_tool_result

logger = logging.getLogger(__name__)

PLAN_TTL_MINUTES = 30


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def is_expired(plan: Dict[str, Any] | None = None) -> bool:
    plan = plan or {}
    created_at = _parse_dt(plan.get("created_at"))
    if created_at is None:
        return False
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) > created_at + timedelta(minutes=PLAN_TTL_MINUTES)


def confirm_plan(
    db, user_id: int, plan: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    """Executa todas as ações do plano em sequência.

    Cada ação vira um `ToolCall` e passa pelo mesmo `execute_tool` do chat
    normal — nenhuma escrita nova é inventada aqui. Retorna os resultados
    formatados para exibir ao usuário.
    """
    plan = plan or {}
    actions = plan.get("actions") or []
    if not actions:
        return {"ok": False, "error": "Nenhuma ação para confirmar.", "results": []}

    results: List[Dict[str, Any]] = []
    ok = True
    for action in actions:
        if not isinstance(action, dict):
            continue
        tool = action.get("tool")
        arguments = action.get("arguments") or {}
        if not tool:
            continue
        tool_call = ToolCall(tool=tool, arguments=arguments)
        try:
            outcome = execute_tool(db, user_id, tool_call)
            results.append(
                {
                    "tool": tool,
                    "ok": True,
                    "message": format_tool_result(outcome["action"], outcome["result"]),
                    "result": outcome["result"],
                }
            )
        except Exception as exc:  # noqa: BLE001 — uma falha não deve abortar as demais
            logger.exception("Falha ao confirmar ação %s (user_id=%s)", tool, user_id)
            ok = False
            results.append({"tool": tool, "ok": False, "message": str(exc)})
    return {"ok": ok, "results": results}


def cancel_plan(
    db, user_id: int, plan: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    return {"ok": True, "cancelled": True}
