# AssistFin — Guia para agentes (Cursor)

Instruções para assistentes de IA que trabalham neste repositório.

## Contexto

AssistFin é finanças pessoais multiusuário com chat híbrido (regras + Groq + Ollama). Dinheiro em **centavos** no banco; UI em pt-BR.

## Antes de codar

1. Leia o [README.md](README.md) e a skill relevante em `.cursor/skills/`.
2. Mudança no agente → `assistfin-ai-agent` + `assistfin-agent-tests`.
3. Mudança financeira → `assistfin-finance-domain` + testes em `tests/test_summary.py`, `tests/test_transfers.py`, `tests/test_update_transfer.py`, `tests/test_planned_transactions.py`, `tests/test_recurrence.py`, `tests/test_installments.py`.
4. Cartões → `assistfin-credit-cards`. Parcelas → `assistfin-installments`.
5. Deploy → `assistfin-deploy-nginx` + `assistfin-implementation`.

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

Wizard de transação (`transaction_slots.py`):

| Status | Ordem resumida |
|--------|----------------|
| **Previsto** | tipo → status → competência + vencimento (se **não** parcelado) → modo → … |
| **Realizado** | tipo → status → modo (se ainda indefinido) → pagamento (se **não** parcelado) → … |
| **Parcelado** | … → N parcelas → intervalo → **parcela atual** (`installment_start_index`) → **competência** + **vencimento** da parcela → pagamento (se realizado) → valor → total vs parcela → descrição → conta → categoria |

Regras de datas no parcelamento: `apply_inferred_dates` não copia `ontem`/`hoje` da mensagem; `payment_date` não altera competência/vencimento já informados; `create_installment_plan` usa `due_date` como âncora do cronograma.

Wizard de realizar previsto (`realize_planned_slots.py`): identifica previsto → data de pagamento → mesma conta? → conta (se diferente).

Corrigir transferência: ferramenta `update_transfer` (origem, destino, valor, data). **Não** usar `update_transaction` nem `register_transfer`.

### Lançamentos fixos

- Tabela `recurring_rules`; transações geradas têm `recurrence_id`
- Motor: `app/services/recurrence.py` — horizonte 3 meses, idempotente
- Encerrar série: `deactivate_recurring_rule()` + rota `POST /transactions/recurring/{rule_id}/stop`
- Responder no slot `payment_mode` ou `is_recurring` **não** cancela o wizard

### Lançamentos parcelados

- Tabela `installment_plans`; transações têm `installment_plan_id` + `installment_index` (1..N)
- Motor: `app/services/installments.py` — skill `assistfin-installments`
- Valor: `installment_amount_basis` = `total` (divide) ou `installment` (repete N vezes)
- Parcela inicial: `installment_start_index` — só cria da parcela informada até N (índices e descrições `k/N` preservados)
- Datas: competência e vencimento da parcela atual no wizard; cronograma a partir do vencimento; caixa (`payment_date`) independente em realizado
- `INSTALLMENT_SLOTS`: `installment_count`, `installment_interval`, `installment_start_index`, `installment_amount_basis`

### Cartões de crédito e faturas

- Entidade `CreditCard` (`credit_cards`) — separada de contas bancárias
- Campos: `closing_day`, `due_day`, `credit_limit_cents`, `settlement_account_id` (conta de liquidação padrão)
- Tabela `card_invoices`; transações têm `card_id` e/ou `account_id`
- Motor: `app/services/credit_cards.py` — skill `assistfin-credit-cards`
- Compra no cartão = despesa na fatura; **não** altera saldo bancário
- Pagar fatura = despesa na conta de débito (liquidação); não duplica despesa da compra
- Assistente: `create_card`, `update_card`, `delete_card`, `list_invoices`, `pay_invoice`
- Wizard de cadastro: `card_wizard.py`

### UI Movimentos (`/transactions`)

| Seção | Conteúdo |
|-------|----------|
| **A realizar** | `status = planned` pendente (`not is_realized`); vencimento; selo `Fixo · …` se recorrente; selo `3/12 · mensal` se parcelado; **Realizar** / **Encerrar série** / **Cancelar parcelas** |
| **Extrato** | Somente `status = actual`; data de pagamento; “de previsto” quando `source_planned_id` |

Previstos liquidados **não** listados (evita duplicata). Pares previsto/realizado no dashboard (`plan_vs_actual`). Consultas separadas: `ListTransactionsInput(status="planned")` e `status="actual"`.

### Wizard vs multi-lançamentos

- Slots de data (`competence_date`, `due_date`, `payment_date`), modo (`payment_mode`) e parcelas (`INSTALLMENT_SLOTS`) / recorrência (`RECURRENCE_SLOTS`) têm prioridade sobre `parse_multi_movements`
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
| Cálculos | `app/services/finance.py`, `app/services/recurrence.py`, `app/services/installments.py`, `app/services/credit_cards.py` |
| Agente | `app/agent/runner.py`, `app/services/tools.py`, `app/agent/prompt.py` |
| Wizards | `transaction_wizard.py`, `transaction_slots.py`, `realize_planned_slots.py`, `account_wizard.py`, `category_wizard.py`, `card_wizard.py`, `transfer_slots.py`, `pay_invoice_slots.py` |
| UI movimentos | `templates/transactions.html`, `routers/pages.py` (`_transactions_page_context`) |
| UI chat | `templates/partials/agent_*.html`, `app/chat_format.py` |
| Auth | `app/auth.py`, `app/routers/auth.py`, `app/main.py` |

## Skills disponíveis

- `assistfin-implementation` — deploy, testes, convenções
- `assistfin-finance-domain` — saldos, períodos, transferências
- `assistfin-ai-agent` — runner, LLM, ferramentas, visual do chat
- `assistfin-installments` — parcelas (total vs parcela, índice, datas)
- `assistfin-onboarding` — primeira conta
- `assistfin-agent-tests` — pytest do agente
- `assistfin-deploy-nginx` — infra e proxy
- `assistfin-credit-cards` — cartões, faturas, ciclo, pagamento
- `ai-agent-design-patterns` — padrões de orquestração (LLM-first, wizards, confirmação)

## Planos em `.cursor/plans/`

Já implementados (não reexecutar): [chat-visual-completo.md](.cursor/plans/chat-visual-completo.md), [valor-total-ou-parcela.md](.cursor/plans/valor-total-ou-parcela.md). Sem briefing pendente.

## Não editar

- Arquivos de plano em `.cursor/plans/` (a menos que o usuário peça)
- `.env` de produção
