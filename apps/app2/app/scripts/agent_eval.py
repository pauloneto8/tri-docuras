"""CLI de avaliação do agente (legado vs v2).

Só executa manualmente, com `GROQ_API_KEY` configurada. Não grava nada: o modo
v2 só produz plano pendente (escritas não executadas) e o modo legado só
resolve a intenção (`_resolve_intent`), sem chamar `execute_tool`.

Uso:
    python -m app.scripts.agent_eval --user-id 1
    python -m app.scripts.agent_eval --user-id 1 --mode both --limit 20
    python -m app.scripts.agent_eval --delay 3   # mais espaçado, se ainda der 429
    python -m app.scripts.agent_eval --dry-run   # só valida o YAML

O tier free do Groq tem 200.000 tokens/dia e cada chamada do v2 custa ~2.800
tokens só de prompt, então os 83 casos não cabem num dia. Rode em lotes com
`--offset`/`--limit`; se o orçamento acabar, o lote para e só os casos já
medidos entram na taxa.

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
    tokens: Optional[Dict[str, int]] = None


def load_cases() -> List[EvalCase]:
    path = Path(__file__).parents[2] / "tests" / "agent_eval" / "cases.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [EvalCase.model_validate(c) for c in (data.get("cases") or [])]


def _norm(value: Any) -> str:
    return str(value).strip().lower().replace(",", ".")


def _as_number(value: Any) -> Optional[float]:
    """Número de `12`, `"12"`, `"12.00"`, `"R$ 12,00"`, `1200` (centavos).

    O LLM escreve o mesmo valor de formas diferentes (`"12"` vs `"12.00"`), e o
    app trata tudo como centavo. Comparar como texto daria falso negativo.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower().replace("r$", "").replace(" ", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _args_match(expected: Dict[str, Any], actual: Dict[str, Any]) -> bool:
    for key, want in expected.items():
        if key not in actual:
            return False
        got = actual[key]
        want_num, got_num = _as_number(want), _as_number(got)
        if want_num is not None and got_num is not None:
            if want_num != got_num:
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
    matched = match_case(case, result.tool_calls, result.response)
    matched.tokens = (result.metrics or {}).get("tokens")
    return matched


async def _run_legacy(db, user_id: int, case: EvalCase) -> CaseResult:
    from app.agent import runner

    context = runner.build_intent_context(db, user_id, {})
    tool_call, _source = await runner._resolve_intent(case.message, context=context)
    calls = (
        [{"tool": tool_call.tool, "arguments": tool_call.arguments}] if tool_call else []
    )
    return match_case(case, calls, "")


def _failed_case(case: EvalCase, exc: Exception) -> CaseResult:
    return CaseResult(
        id=case.id,
        message=case.message,
        matched=False,
        details=f"erro ao executar o caso: {type(exc).__name__}: {exc}",
    )


async def _run_case(runner_fn, *args) -> CaseResult:
    """Um caso que estoura (rede, erro do agente) conta como falha, não aborta a corrida.

    `GroqRateLimitError` sempre propaga: o chamador decide, porque só o 429 de
    orçamento diário deve parar o lote — 429 por minuto é o caso falhando, não
    o lote.
    """
    from app.agent.groq import GroqRateLimitError

    try:
        return await runner_fn(*args)
    except GroqRateLimitError:
        raise
    except Exception as exc:  # noqa: BLE001 — o relatório mostra o caso que quebrou
        return _failed_case(args[-1], exc)


def _is_daily_quota(exc: Exception) -> bool:
    """429 de orçamento diário (o lote parou) ou só de taxa por minuto (o caso falhou).

    Mesmo critério de `app/agent/groq.py::_is_daily_quota`: o free tier tem
    8.000 tokens/min **e** 200.000/dia por modelo, e os dois aparecem como 429.
    """
    response = getattr(exc, "response", None)
    if response is None:
        return False
    body = response.text.lower()
    return "tokens per day" in body or "(tpd)" in body


def _print_summary(label: str, results: List[CaseResult]) -> float:
    total = len(results)
    ok = sum(1 for r in results if r.matched)
    rate = (ok / total) if total else 0.0
    print(f"\n=== {label}: {ok}/{total} ({rate:.1%}) ===")
    for r in results:
        mark = "OK " if r.matched else "FAIL"
        print(f"  [{mark}] {r.id}: {r.message!r}")
        if r.tokens:
            print(
                f"        tokens: {r.tokens.get('total', 0)} "
                f"(prompt={r.tokens.get('prompt', 0)}, "
                f"completion={r.tokens.get('completion', 0)}, "
                f"cache={r.tokens.get('cached', 0)})"
            )
        if not r.matched:
            print(f"        esperado não bateu. chamadas={json.dumps(r.calls, ensure_ascii=False)}")
            if r.details:
                print(f"        {r.details}")
    medidos = [r.tokens for r in results if r.tokens]
    if medidos:
        total = sum(t.get("total", 0) for t in medidos)
        prompt = sum(t.get("prompt", 0) for t in medidos)
        cache = sum(t.get("cached", 0) for t in medidos)
        media = total / len(medidos)
        print(
            f"  tokens: {total} no lote | média {media:.0f} por caso "
            f"(prompt {prompt}, cache {cache})"
        )
    return rate


async def run(
    user_id: int,
    mode: str,
    limit: Optional[int],
    threshold: float,
    delay: float,
    offset: int = 0,
) -> int:
    if not os.getenv("GROQ_API_KEY"):
        print("GROQ_API_KEY não definido; execução manual apenas.", file=sys.stderr)
        return 1

    from app.agent.groq import GroqRateLimitError
    from app.db import SessionLocal

    cases = load_cases()
    if offset:
        cases = cases[offset:]
    if limit:
        cases = cases[:limit]
    print(
        f"Casos: {len(cases)} | modo: {mode} | user_id: {user_id} | "
        f"pausa: {delay}s | offset: {offset}"
    )

    db = SessionLocal()
    try:
        v2_rate = legacy_rate = None
        selected = cases
        out_of_budget = False
        if mode in {"v2", "both"}:
            results = []
            for case in cases:
                try:
                    results.append(await _run_case(_run_v2, db, user_id, case))
                except GroqRateLimitError as exc:
                    if not _is_daily_quota(exc):
                        results.append(_failed_case(case, exc))
                        await asyncio.sleep(delay)
                        continue
                    print(
                        f"\nOrcamento diario do Groq esgotado no caso {case.id}; "
                        f"lote interrompido com {len(results)} casos medidos."
                    )
                    out_of_budget = True
                    break
                await asyncio.sleep(delay)
            v2_rate = _print_summary("v2", results)
            # No modo "both" o legado roda só os casos que o v2 chegou a medir,
            # senão a comparação v2 x legado fica injusta.
            if mode == "both":
                measured = {r.id for r in results}
                selected = [c for c in cases if c.id in measured]
        if mode in {"legacy", "both"} and out_of_budget:
            # O legado também chama o Groq (`call_intent_llm`) e engole o 429
            # devolvendo "nenhuma ferramenta": medir agora contaria cada caso
            # como falha do legado e inflaria o v2. Fica para outro dia.
            print(
                "\nLegado não medido: o modelo está sem orçamento diário (o legado "
                "também usa o Groq). Rode `--mode legacy` quando a cota voltar."
            )
        elif mode in {"legacy", "both"}:
            results = []
            for case in selected:
                try:
                    results.append(await _run_case(_run_legacy, db, user_id, case))
                except GroqRateLimitError as exc:
                    if not _is_daily_quota(exc):
                        results.append(_failed_case(case, exc))
                        await asyncio.sleep(delay)
                        continue
                    print(
                        f"\nOrcamento diario do Groq esgotado no caso legado {case.id}; "
                        f"lote interrompido com {len(results)} casos medidos."
                    )
                    break
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
        "--delay",
        type=float,
        default=45.0,
        help="pausa entre casos. O free tier do Groq aceita 8.000 tokens/min e um caso "
        "do v2 gasta ~10.000 tokens em 2-4 chamadas: abaixo de ~45s ele toma 429 por "
        "minuto e o próprio retry do cliente segura o caso (até 30s por tentativa)",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="pula os N primeiros casos — o orcamento diario do Groqfree nao roda "
        "os 83 de uma vez;rode em lotes (ex.: --offset 0, depois 15, 30…)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cases = load_cases()
    if args.dry_run:
        print(f"YAML válido: {len(cases)} casos carregados.")
        return 0
    return asyncio.run(
        run(args.user_id, args.mode, args.limit, args.threshold, args.delay, args.offset)
    )


if __name__ == "__main__":
    raise SystemExit(main())
