# AssistFin — Guia para agentes (Cursor)

Instruções para assistentes de IA que trabalham neste repositório.

## Contexto

AssistFin é finanças pessoais multiusuário com chat híbrido (regras + Groq + Ollama). Dinheiro em **centavos** no banco; UI em pt-BR.

## Antes de codar

1. Leia o [README.md](README.md) e a skill relevante em `.cursor/skills/`.
2. Mudança no agente → `assistfin-ai-agent` + `assistfin-agent-tests`.
3. Mudança financeira → `assistfin-finance-domain` + testes em `tests/test_summary.py`, `tests/test_transfers.py`, `tests/test_planned_transactions.py`.
4. Deploy → `assistfin-deploy-nginx` + `assistfin-implementation`.

## Regras de ouro

- **Escopo mínimo** — não refatorar além do pedido.
- **Nunca** commitar `.env`, chaves ou `SECRET_KEY`.
- **Nunca** calcular saldos no LLM — só em `finance.py`.
- Transferências **nunca** somam em receitas/despesas do período.
- Escritas no agente exigem **confirmação** (`WRITE_TOOLS` em `runner.py`).
- Após mudanças: `docker compose build app2 && docker compose up -d app2` e `pytest -q` no container.

## Domínio financeiro (resumo)

| Tipo | `Transaction.type` | Período (receitas/despesas) | Saldo da conta |
|------|---------------------|----------------------------|----------------|
| Despesa | `expense` | Despesa | − |
| Receita | `income` | Receita | + |
| Transferência saída | `transfer_out` | — | − |
| Transferência entrada | `transfer_in` | — | + |

Dashboard: `get_summary()` com `period` + `ref_date`. Saldos por conta usam `account_balances(as_of=period_end)`.

### Datas de movimento

| Campo | Uso |
|-------|-----|
| `competence_date` | Mês a que o lançamento pertence (orçamentos) |
| `due_date` | Vencimento; previstos entram na projeção por esta data |
| `payment_date` | Quando o caixa se moveu (somente `actual`) |
| `transaction_date` | Data de caixa no sistema (= `due_date` ou `payment_date`) |

Wizard de transação (`transaction_slots.py`): após tipo e status, pergunta datas antes de valor/descrição/conta/categoria.

### UI Movimentos (`/transactions`)

| Seção | Conteúdo |
|-------|----------|
| **A realizar** | `status = planned` pendente (`not is_realized`); vencimento; ação **Realizar** |
| **Extrato** | Somente `status = actual`; data de pagamento; “de previsto” quando `source_planned_id` |

Previstos liquidados **não** listados (evita duplicata). Pares previsto/realizado no dashboard (`plan_vs_actual`). Consultas separadas: `ListTransactionsInput(status="planned")` e `status="actual"`.

### Wizard vs multi-lançamentos

- Slots de data (`competence_date`, `due_date`, `payment_date`) têm prioridade sobre `parse_multi_movements`
- `is_date_only_message()` — data isolada (`10/08/2026`) não vira vários lançamentos
- Testes: `tests/test_multi_movements.py`

## Checklist de feature

1. Modelo + migração Alembic (se persistir)
2. `finance.py` + `schemas.py`
3. Agente: `ToolCall`, `execute_tool`, `format_tool_result`, `prompt.py`, `intents.py`
4. UI (templates) se aplicável
5. Testes
6. Rebuild + pytest no container

## Arquivos críticos

| Área | Arquivos |
|------|----------|
| Cálculos | `app/services/finance.py` |
| Agente | `app/agent/runner.py`, `app/services/tools.py` |
| Wizards | `transaction_wizard.py`, `transaction_slots.py`, `account_wizard.py`, `category_wizard.py`, `transfer_slots.py` |
| UI movimentos | `templates/transactions.html`, `routers/pages.py` (`_transactions_page_context`) |
| UI chat | `templates/partials/agent_*.html` |
| Auth | `app/auth.py`, `app/routers/auth.py`, `app/main.py` |

## Skills disponíveis

- `assistfin-implementation` — deploy, testes, convenções
- `assistfin-finance-domain` — saldos, períodos, transferências
- `assistfin-ai-agent` — runner, LLM, ferramentas
- `assistfin-onboarding` — primeira conta
- `assistfin-agent-tests` — pytest do agente
- `assistfin-deploy-nginx` — infra e proxy
- `ai-agent-design-patterns` — padrões de agentes

## Não editar

- Arquivos de plano em `.cursor/plans/` (a menos que o usuário peça)
- `.env` de produção
