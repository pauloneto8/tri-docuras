# Referência — parcelas

## Migração 014

- `installment_plans`: user_id, account_id, category_id, type, total_cents, installment_count, interval, start_date, description, is_active
- `transactions.installment_plan_id`, `installment_index`
- Check: `interval IN ('monthly','weekly','biweekly')`

## API interna

```python
from app.services.installments import (
    split_cents,
    repeat_cents,
    create_installment_plan,
    cancel_installment_plan,
)

amounts = split_cents(10001, 3)  # [3333, 3333, 3335]
units = repeat_cents(10000, 12)   # [10000] * 12

plan, txs = create_installment_plan(
    db, user_id,
    account_id=...,
    total_cents=9500,
    installment_count=360,
    interval="monthly",
    start_date=date(2026, 9, 30),  # vencimento da parcela atual
    description="Prestação",
    competence_date=date(2026, 9, 30),
    due_date=date(2026, 9, 30),
    payment_date=date(2026, 9, 2),  # caixa (realizado); opcional
    amount_basis="installment",
    start_index=180,  # cria 180..360
    first_status="actual",
)
```

## Schemas (`RegisterExpenseInput` / `RegisterIncomeInput`)

| Campo | Uso |
|-------|-----|
| `installment_count` | Total de parcelas do plano (ex.: 360) |
| `installment_interval` | `monthly` \| `weekly` \| `biweekly` |
| `installment_start_index` | Parcela que o usuário está lançando (1…N) |
| `installment_amount_basis` | `total` \| `installment` |

## UI Movimentos

- Checkbox **Parcelado** (exclusivo com fixo)
- Selo `3/12 · mensal` via `installment_label`
- Radios **total da compra** / **valor de cada parcela** (`installment_amount_basis`)
- Parcela inicial (`installment_start_index`) só no wizard do assistente; o formulário cria da parcela 1
- `POST /transactions/installments/{plan_id}/stop`

## Wizard — perguntas da parcela

Geradas em `_question_for_slot` quando `payment_mode == installment`:

- Competência: *"Qual a competência da parcela X/N…?"*
- Vencimento: *"Qual o vencimento da parcela X/N? As demais serão calculadas a partir desta data."*

## Reset de dados

Incluir `DELETE FROM installment_plans` antes de `transactions` (FK). Ver [docs/OPERATIONS.md](../../../docs/OPERATIONS.md).
