# Referência — cartões e faturas

## Modelo

- `credit_cards`: `name`, `institution`, `credit_limit_cents`, `closing_day`, `due_day`, `settlement_account_id`, `is_active`
- `card_invoices`: `card_id`, ciclo, vencimento, status (`open`|`closed`|`paid`)
- `transactions`: `card_id` (opcional), `account_id` (opcional), `invoice_id` (compras no cartão)

Legado: contas `account_type=cartao` migradas para `credit_cards` na revisão `016` e desativadas.

## API interna (`finance.py`)

```python
finance.create_card(db, user_id, CreateCardInput(...))
finance.update_card(db, user_id, UpdateCardInput(...))
finance.deactivate_card(db, user_id, DeleteCardInput(...))
finance.find_card(db, user_id, card_id=..., card_name=...)
```

```python
from app.services.credit_cards import (
    cycle_for_purchase,
    pay_invoice,
    list_invoices,
    format_credit_card,
    ensure_invoices_for_card,
    invoice_dashboard,
)
```

## Schemas

```python
CreateCardInput(name, closing_day, due_day, settlement_account_name, institution?, credit_limit?)
UpdateCardInput(card_id?, card_name?, name?, institution?, credit_limit?, closing_day?, due_day?, settlement_account_name?)
DeleteCardInput(card_id?, card_name?)
```

## Assistente — argumentos

| Ferramenta | Identificação | Campos editáveis |
|------------|---------------|------------------|
| `create_card` | wizard pergunta tudo | name, institution, closing_day, due_day, credit_limit, settlement_account_name |
| `update_card` | `card_id` ou `card_name` | name, institution, credit_limit, closing_day, due_day, settlement_account_name |
| `delete_card` | `card_id` ou `card_name` | — |
| `pay_invoice` | `account_name` ou `invoice_id` | `from_account_name`, `payment_date?` |

## UI

- `/` — dashboard com seção **Cartões e faturas** (`summary.card_invoices`)
- `/accounts/cards` — lista de cartões com fatura atual e limite disponível
- Formulário **Novo cartão** com conta de liquidação obrigatória
- **Pagar fatura** por cartão/fatura

## Reset de dados

```sql
DELETE FROM transactions;
DELETE FROM card_invoices;
DELETE FROM credit_cards;
```

(após transações, por causa de `invoice_id` / `card_id`)
