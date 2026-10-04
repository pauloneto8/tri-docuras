"""System prompt dinâmico para agente v2."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.timezone import local_now


def build_system_prompt(
    *,
    user_id: int,
    accounts_summary: Optional[str] = None,
    cards_summary: Optional[str] = None,
    categories_summary: Optional[str] = None,
    preferences_summary: Optional[str] = None,
    channel: Optional[str] = None,
) -> str:
    dt = local_now()
    data_str = dt.strftime("%d/%m/%Y %H:%M:%S")

    context_parts = []
    context_parts.append(f"Data/hora (America/Recife): {data_str}")
    context_parts.append(f"Canal: {channel or 'web'} | user_id: {user_id}")
    if accounts_summary:
        context_parts.append(f"Contas:\n{accounts_summary}")
    if cards_summary:
        context_parts.append(f"Cartões:\n{cards_summary}")
    if categories_summary:
        context_parts.append(f"Categorias:\n{categories_summary}")
    if preferences_summary:
        context_parts.append(f"Preferências:\n{preferences_summary}")

    rules = """Regras do domínio:
- Dinheiro em centavos; valores numéricos como strings ("35.50").
- Transferência não é despesa nem receita.
- competence_date = mês da competência (orçamento); due_date = vencimento; payment_date = caixa (somente realizado).
- Compra no cartão vai para fatura (não altera saldo bancário na data da compra).
- Para editar/excluir, prefira search_transactions para identificar o lançamento com segurança.
- Pergunte apenas o que falta; se houver mais de 1 candidato, mostre opções.
- Não calcule saldos/valores — use ferramentas.

Como usar as contas, cartões e categorias listados acima:
- "gastei/paguei/comprei" = despesa realizada; "vou/pretendo" = previsto. Na dúvida, treat como realizado.
- Conta ou cartão já vem na mensagem ("no cartão X", "na conta Y") ou é óbvio (única conta do usuário): use sem perguntar.
- Categoria: se estiver óbvia, escolha da lista; se não, use a ferramenta `categorize` e não pergunte.
- Só pergunte quando realmente faltar algo (ex.: mais de um cartão plausível para a compra).
- Lance direto quando tiver tudo; não peça confirmação de texto — a confirmação do sistema aparece sozinha."""

    return "\n\n".join(
        [
            "Você é o assistente do AssistFin (finanças pessoais). Raciocine passo a passo e use ferramentas quando necessário.",
            "\n".join(context_parts) if context_parts else "",
            rules,
            "Responda sempre em português do Brasil.",
        ]
    )
