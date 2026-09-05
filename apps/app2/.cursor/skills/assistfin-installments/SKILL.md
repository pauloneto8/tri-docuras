---
name: assistfin-installments
description: >-
  Lançamentos parcelados no AssistFin: N parcelas com intervalo mensal,
  semanal ou quinzenal; parcela inicial parcial; valor total vs parcela;
  datas de competência/vencimento no wizard; cancelamento do plano.
  Use ao implementar parcelas, 12x, em N vezes, quinzenal, installment_plans
  ou alterar wizard/UI de Movimentos relacionado a parcelamento.
paths: app/services/installments.py, app/services/finance.py, app/models.py, app/services/transaction_slots.py, app/templates/transactions.html, app/routers/pages.py, tests/test_installments.py
---

# AssistFin — Lançamentos parcelados

## Regras

- Valor informado pode ser o **total da compra** (`amount_basis=total`, divide; resto na última) ou o **valor de cada parcela** (`installment`, repete N vezes). Wizard e formulário Movimentos: `installment_amount_basis`.
- **Parcela inicial** (`installment_start_index`): usuário informa qual parcela está lançando (1…N). Só são criadas transações de `start_index` até N; índices e `k/N` na descrição preservados.
- **Datas no wizard (parcelado):**
  - Perguntar competência e vencimento **da parcela atual** após N, intervalo e índice.
  - Cronograma: `create_installment_plan` usa `due_date` como `start_date`; demais vencimentos via `due_date_for_index`.
  - Realizado: `payment_date` é quando o caixa moveu — **não** sobrescreve competência/vencimento (`fill_slot` em `payment_date`).
  - `apply_inferred_dates` **não** roda para `payment_mode=installment`; ao escolher *parcelado*, limpar datas genéricas (`_clear_installment_schedule_dates`).
- Intervalos: `monthly`, `weekly`, `biweekly` (quinzenal).
- Parcelas futuras = `planned`; parcela em `start_index` pode ser `actual` se status realizado.
- `installment_plan_id` + `installment_index` (1..N); unique `(plan_id, index)`.
- Mutuamente exclusivo com `frequency` (fixo). Transferências **não** parcelam.
- Realizar uma parcela **não** altera as demais.

## Arquivos

| Arquivo | Papel |
|---------|--------|
| `app/services/installments.py` | `split_cents`, `repeat_cents`, `due_date_for_index`, `create_installment_plan`, `cancel_installment_plan` |
| `app/services/finance.py` | `_register_installment_movement`, `register_expense/income` |
| `app/services/transaction_slots.py` | Wizard: slots, `_next_slot`, perguntas da parcela |
| Migração `014` | `installment_plans`, colunas em `transactions` |

## Wizard

**Previsto (não parcelado):** tipo → status → competência → vencimento → modo → …

**Realizado (não parcelado):** tipo → status → modo → data da realização → …

**Parcelado** (após status; em realizado, modo vem antes de pagamento):

`installment_count` → `installment_interval` → `installment_start_index` → `competence_date` → `due_date` → (`payment_date` se realizado) → `amount` → `installment_amount_basis` → descrição → conta → categoria

`INSTALLMENT_SLOTS` nas guardas anti-multi e cancelamento global (como `RECURRENCE_SLOTS`).

LLM **não** envia: `status`, `installment_amount_basis`, `installment_start_index`.

Formulário Movimentos: N + intervalo + radios total/parcela. **Não** pede parcela inicial (sempre 1).

## Testes

`tests/test_installments.py` — split, repeat, parcela inicial parcial, datas (competência/vencimento vs pagamento), wizard, cancelar plano.

## Referência

[reference.md](reference.md)
