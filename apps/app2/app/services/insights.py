"""Insight financeiro proativo (Fase 2 do plano `.cursor/plans/agente-inteligencia-proativa.md`).

Gera um texto curto de 2-3 frases a partir dos números que `finance.get_summary`
e `finance.get_budget_status` já calculam. O Claude só recebe valores já
formatados em BRL e explica/comenta — nunca calcula. Depois de gerar, valida
que todo valor monetário citado no texto é um dos valores enviados (evaluator
simples, sem segunda chamada de LLM) antes de salvar; se algum número não
bater, descarta o insight em vez de arriscar mostrar um valor inventado.
"""

import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.claude import call_claude
from app.config import settings
from app.models import AgentInsight, User
from app.schemas import BudgetStatusInput, SummaryInput
from app.services import finance
from app.timezone import local_today

logger = logging.getLogger(__name__)

INSIGHT_SYSTEM_PROMPT = """Voce e o assistente do AssistFin (financas pessoais).
Escreva um insight curto (2 a 3 frases, portugues do Brasil, tom direto e gentil)
sobre o mes do usuario, usando SOMENTE os numeros fornecidos abaixo.
Copie os valores monetarios EXATAMENTE como estao formatados (ex.: R$ 1.234,56)
— nao arredonde, nao recalcule, nao invente nenhum valor que nao esteja na lista.
Nao sugira falar com contador ou consultor. Responda so com o texto do insight,
sem markdown, sem aspas."""

_MONEY_RE = re.compile(r"R\$\s?-?\d{1,3}(?:\.\d{3})*,\d{2}")


def _build_prompt(summary: dict, budgets: list[dict]) -> tuple[str, set[str]]:
    known: set[str] = set()
    lines = [
        f"Periodo: {summary['period_label']}",
        f"Receita: {summary['income']}",
        f"Despesa: {summary['expense']}",
        f"Saldo do periodo: {summary['balance']}",
        f"Saldo projetado ao fim do periodo: {summary['projected_ending_balance']}",
    ]
    known.update(
        {
            summary["income"],
            summary["expense"],
            summary["balance"],
            summary["projected_ending_balance"],
        }
    )
    for item in budgets:
        lines.append(
            f"Orcamento {item['category']}: gasto {item['spent']} de {item['limit']} "
            f"({item['percent_used']}%)"
        )
        known.add(item["spent"])
        known.add(item["limit"])
    return "\n".join(lines), known


def _validate(text: str, known_values: set[str]) -> bool:
    mentions = _MONEY_RE.findall(text)
    return all(mention in known_values for mention in mentions)


async def generate_monthly_insight(
    db: Session, user: User, *, year: int | None = None, month: int | None = None
) -> AgentInsight | None:
    """Gera (e salva) o insight do mes para um usuario. Retorna None se a
    funcionalidade estiver desligada, sem chave configurada, ou se a resposta
    do modelo falhar na validacao de valores."""
    if not settings.enable_ai_insights:
        return None

    today = local_today()
    year = year or today.year
    month = month or today.month

    summary = finance.get_summary(db, user.id, SummaryInput(year=year, month=month, period="month"))
    budgets = finance.get_budget_status(db, user.id, BudgetStatusInput(year=year, month=month))

    prompt, known_values = _build_prompt(summary, budgets)

    try:
        text = await call_claude(prompt, system_prompt=INSIGHT_SYSTEM_PROMPT, max_tokens=300)
    except Exception:  # noqa: BLE001 — erro de rede/API não deve derrubar o job
        logger.exception("Falha ao chamar Claude para insight (user_id=%s)", user.id)
        return None

    if not text:
        return None

    if not _validate(text, known_values):
        logger.warning(
            "Insight descartado por citar valor fora do esperado (user_id=%s): %r",
            user.id,
            text,
        )
        return None

    return save_insight(db, user_id=user.id, year=year, month=month, text=text)


def save_insight(
    db: Session, *, user_id: int, year: int, month: int, text: str, source: str = "claude-insight"
) -> AgentInsight:
    existing = db.scalar(
        select(AgentInsight).where(
            AgentInsight.user_id == user_id,
            AgentInsight.year == year,
            AgentInsight.month == month,
        )
    )
    if existing:
        existing.text = text
        existing.source = source
        db.flush()
        return existing

    insight = AgentInsight(user_id=user_id, year=year, month=month, text=text, source=source)
    db.add(insight)
    db.flush()
    return insight


def get_latest_insight(db: Session, user_id: int) -> AgentInsight | None:
    return db.scalar(
        select(AgentInsight)
        .where(AgentInsight.user_id == user_id)
        .order_by(AgentInsight.year.desc(), AgentInsight.month.desc(), AgentInsight.created_at.desc())
        .limit(1)
    )
