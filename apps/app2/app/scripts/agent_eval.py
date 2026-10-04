"""CLI de avaliação do agente (legado vs v2).

Só executa manualmente, com `GROQ_API_KEY` configurada. Não grava nada: o modo
v2 só produz plano pendente (escritas não executadas) e o modo legado só
resolve a intenção (`_resolve_intent`), sem chamar `execute_tool`.

Uso:
    python -m app.scripts.agent_eval --user-id 1
    python -m app.scripts.agent_eval --user-id 1 --mode both --limit 20
    python -m app.scripts.agent_eval --delay 3   # mais espaçado, se ainda der 429
    python -m app.scripts.agent_eval --dry-run   # só valida o YAML

Critério (Fase 0 do plano): v2 >= legado e acerto >= 90%.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field


class ExpectedTool(BaseModel):
    tool: str
    args: Dict[str, Any] = Field(default_factory=dict)


class EvalCase(BaseModel):
    id: str
    message: str
    expected_tools: List[ExpectedTool] = Field(default_factory=list)
    expected_reads: List[str] = Field(default_factory=list)
    answer: bool = False
    context: Dict[str, Any] = Field(default_factory=dict)


class CaseResult(BaseModel):
    id: str
    message: str
    matched: bool
    calls: List[Dict[str, Any]] = Field(default_factory=list)
    response: str = ""
    details: str = ""


def load_cases() -> List[EvalCase]:
    path = Path(__file__).parents[2] / "tests" / "agent_eval" / "cases.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [EvalCase.model_validate(c) for c in (data.get("cases") or [])]


def _norm(value: Any) -> str:
    return str(value).strip().lower().replace(",", ".")


def _args_match(expected: Dict[str, Any], actual: Dict[str, Any]) -> bool:
    for key, want in expected.items():
        if key not in actual:
            return False
        got = actual[key]
        if isinstance(want, (int, float)) and isinstance(got, (int, float)):
            if float(want) != float(got):
                return False
        elif _norm(want) != _norm(got):
            return False
    return True


def match_case(case: EvalCase, calls: List[Dict[str, Any]], response: str) -> CaseResult:
    names = [c.get("tool") for c in calls]
    details: List[str] = []
    matched = True

    for read in case.expected_reads:
        if read not in names:
            matched = False
            details.append(f"leitura ausente: {read}")

    for expected in case.expected_tools:
        candidates = [c for c in calls if c.get("tool") == expected.tool]
        if not candidates:
            matched = False
            details.append(f"ferramenta ausente: {expected.tool}")
            continue
        if expected.args and not any(
            _args_match(expected.args, c.get("arguments") or {}) for c in candidates
        ):
            matched = False
            details.append(f"args divergentes em {expected.tool}: {expected.args}")

    if case.answer and not response.strip():
        matched = False
        details.append("resposta final vazia")

    return CaseResult(
        id=case.id,
        message=case.message,
        matched=matched,
        calls=[{"tool": c.get("tool"), "arguments": c.get("arguments")} for c in calls],
        response=response,
        details="; ".join(details),
    )


async def _run_v2(db, user_id: int, case: EvalCase) -> CaseResult:
    from app.agent import brain

    result = await brain.run(db=db, user_id=user_id, message=case.message, channel="eval")
    return match_case(case, result.tool_calls, result.response)


async def _run_legacy(db, user_id: int, case: EvalCase) -> CaseResult:
    from app.agent import runner

    context = runner.build_intent_context(db, user_id, {})
    tool_call, _source = await runner._resolve_intent(case.message, context=context)
    calls = (
        [{"tool": tool_call.tool, "arguments": tool_call.arguments}] if tool_call else []
    )
    return match_case(case, calls, "")


async def _run_case(runner_fn, *args) -> CaseResult:
    """Um caso que estoura (rate limit, rede) conta como falha, não aborta a corrida."""
    try:
        return await runner_fn(*args)
    except Exception as exc:  # noqa: BLE001 — o relatório mostra o caso que quebrou
        case = args[-1]
        return CaseResult(
            id=case.id,
            message=case.message,
            matched=False,
            details=f"erro ao executar o caso: {type(exc).__name__}: {exc}",
        )


def _print_summary(label: str, results: List[CaseResult]) -> float:
    total = len(results)
    ok = sum(1 for r in results if r.matched)
    rate = (ok / total) if total else 0.0
    print(f"\n=== {label}: {ok}/{total} ({rate:.1%}) ===")
    for r in results:
        mark = "OK " if r.matched else "FAIL"
        print(f"  [{mark}] {r.id}: {r.message!r}")
        if not r.matched:
            print(f"        esperado não bateu. chamadas={json.dumps(r.calls, ensure_ascii=False)}")
            if r.details:
                print(f"        {r.details}")
    return rate


async def run(user_id: int, mode: str, limit: Optional[int], threshold: float, delay: float) -> int:
    if not os.getenv("GROQ_API_KEY"):
        print("GROQ_API_KEY não definido; execução manual apenas.", file=sys.stderr)
        return 1

    from app.db import SessionLocal

    cases = load_cases()
    if limit:
        cases = cases[:limit]
    print(f"Casos: {len(cases)} | modo: {mode} | user_id: {user_id} | pausa: {delay}s")

    db = SessionLocal()
    try:
        v2_rate = legacy_rate = None
        if mode in {"v2", "both"}:
            results = []
            for case in cases:
                results.append(await _run_case(_run_v2, db, user_id, case))
                await asyncio.sleep(delay)
            v2_rate = _print_summary("v2", results)
        if mode in {"legacy", "both"}:
            results = []
            for case in cases:
                results.append(await _run_case(_run_legacy, db, user_id, case))
                await asyncio.sleep(delay)
            legacy_rate = _print_summary("legado", results)
    finally:
        db.close()

    failed = False
    if v2_rate is not None:
        if v2_rate < threshold:
            print(f"\nFALHA: acerto v2 {v2_rate:.1%} < {threshold:.0%}")
            failed = True
        if legacy_rate is not None and v2_rate < legacy_rate:
            print(f"\nFALHA: v2 {v2_rate:.1%} < legado {legacy_rate:.1%}")
            failed = True
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Avaliação do agente AssistFin")
    parser.add_argument("--user-id", type=int, default=1)
    parser.add_argument("--mode", choices=["v2", "legacy", "both"], default="v2")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--threshold", type=float, default=0.9)
    parser.add_argument(
        "--delay", type=float, default=1.5, help="pausa entre casos, para o rate limit"
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cases = load_cases()
    if args.dry_run:
        print(f"YAML válido: {len(cases)} casos carregados.")
        return 0
    return asyncio.run(
        run(args.user_id, args.mode, args.limit, args.threshold, args.delay)
    )


if __name__ == "__main__":
    raise SystemExit(main())
