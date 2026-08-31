---
name: assistfin-finance-domain
description: >-
  Domínio financeiro do AssistFin: saldos, centavos, contas, transações,
  transferências, orçamentos e regras de negócio. Use ao alterar dashboard,
  finance.py, modelos, onboarding, contas, movimentos, resumos por período
  ou saldo inicial com data.
paths: app/services/finance.py, app/models.py, app/schemas.py, app/services/recurrence.py, app/templates/dashboard.html, app/templates/accounts.html, app/templates/transactions.html, app/templates/budgets.html, app/routers/pages.py, tests/test_summary.py, tests/test_transfers.py, tests/test_planned_transactions.py, tests/test_recurrence.py
---

# AssistFin — Domínio financeiro

## Princípios de dinheiro

- Valores em **centavos** (`*_cents`, `BigInteger`).
- Exibição: `format_brl()` em `schemas.py` (ex.: `1.234,56`).
- Entrada aceita `45,90`, `1.250,00`, `R$ 45.90`.

## Tipos de movimento

| Tipo | `Transaction.type` | Receitas/despesas do período | Saldo da conta |
|------|---------------------|------------------------------|----------------|
| Despesa | `expense` | Despesa | − |
| Receita | `income` | Receita | + |
| Transferência saída | `transfer_out` | **Não** | − |
| Transferência entrada | `transfer_in` | **Não** | + |

Transferências são pares vinculados por `transfer_group_id` (origem + destino).

## Previsto vs realizado

| Status | `payment_date` | Efeito no saldo | Período (receitas/despesas) |
|--------|----------------|-----------------|------------------------------|
| `planned` | `NULL` | Nenhum | Previstos no dashboard (projeção) |
| `actual` | Obrigatório | Sim (`transaction_date`) | Sim |

Realizar: `realize_planned()` cria lançamento `actual` com `source_planned_id`. O previsto permanece no banco para o dashboard. Se a conta informada difere, atualiza `planned.account_id`.

## UI Movimentos (`/transactions`)

| Seção | Query / regra | Exibição |
|-------|---------------|----------|
| **A realizar** | `status=planned`, `not is_realized` | Vencimento; selo Previsto ou `Fixo · mensal/semanal/diária`; ação Realizar / Encerrar série |
| **Extrato** | `status=actual` | Pagamento; selo Realizado; “de previsto” se `source_planned_id` |

Previstos liquidados **não** aparecem na lista. `ListTransactionsInput.status`: `actual` | `planned` | `all` (default `all` — chat/API inalterados).

Formulário manual: realizado → data da realização; previsto → competência + vencimento; **fixo** → frequência + término opcional. **Realizar**: pagamento obrigatório; valor/descrição opcionais; mesma conta ou outra conta.

## Lançamentos fixos

- Tabela `recurring_rules`; transações geradas têm `recurrence_id`.
- Frequências: `daily`, `weekly`, `monthly`. Horizonte: `min(end_date, hoje + 3 meses)`.
- `ensure_recurring_horizon()` idempotente; `deactivate_recurring_rule()` encerra série e apaga previstos pendentes.
- Realizar uma ocorrência **não** encerra a série; reabastece o horizonte se necessário.

## Datas de movimento

| Campo | Papel |
|-------|-------|
| `competence_date` | Mês de competência — **orçamentos** somam por esta data |
| `due_date` | Vencimento — previstos pendentes na projeção |
| `payment_date` | Data de caixa (somente realizado) |
| `transaction_date` | Data de caixa no sistema (= `due_date` ou `payment_date`) |

`resolve_transaction_dates()` em `finance.py` é a fonte da verdade para normalização.

## Conceitos de saldo no dashboard

| Card | Significado |
|------|-------------|
| Receitas | Soma `income` no período |
| Despesas | Soma `expense` no período |
| Resultado do período | Receitas − despesas |
| Saldo anterior | Soma dos saldos das contas no dia anterior ao período |
| Resultado final | Soma dos saldos ao fim do período |
| Saldos por conta | `_account_balance_at(account, period_end)` |

**Saldo inicial** (`opening_balance_cents` + `opening_balance_date`): entra no saldo da conta, não é receita do período. Só vale a partir da data declarada.

## Períodos

`SummaryInput(period="day"|"week"|"month", ref_date=...)`

- `resolve_period_bounds()` define início/fim
- `shift_ref_date()` navega anterior/próximo

## Entidades

- Contas: `corrente`, `poupanca`, `carteira`, `cartao`
- Categorias: `expense` | `income`
- Isolamento por `user_id`

## Ao implementar

1. `finance.py` (fonte da verdade)
2. `format_tool_result` se o agente expõe
3. Templates com rótulos claros
4. Testes (`test_summary.py`, `test_transfers.py`, `test_planned_transactions.py`, `test_recurrence.py`)

## Armadilhas

- `list_accounts` ≠ `list_transactions` (intents)
- Transferência ≠ despesa/receita nos cards do período
- Página `/accounts` = saldo **atual**; dashboard = saldo **histórico** ao fim do período
- Página `/transactions` = **A realizar** + **Extrato**; não misturar previsto liquidado com realizado na lista
- Lançamentos exigem confirmação no agente

## Referência

[reference.md](reference.md)
