# Referência — cartões e faturas

## Modelo

- `credit_cards`: `name`, `institution`, `credit_limit_cents`, `closing_day`, `due_day`, `settlement_account_id`, `is_active`
- `card_invoices`: `card_id`, ciclo, vencimento, status (`open`|`closed`|`paid`)
- `transactions`: `card_id` (opcional), `account_id` (opcional), `invoice_id` (compras no cartão), `ofx_fitid` (idempotência de importação)
- `ofx_import_batches` / `ofx_import_lines`: staging da revisão OFX (`pending` → `applied`|`cancelled`)

Legado: contas `account_type=cartao` migradas para `credit_cards` na revisão `016` e desativadas.
Migração `017`: `ofx_fitid` + tabelas de importação.
Migração `018`: `ofx_category_memory` + categoria nas linhas do lote.

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

## Importação OFX (`ofx_card_import.py`)

```python
from app.services.ofx_card_import import (
    parse_ofx,
    create_batch,
    get_batch,
    batch_review_context,
    apply_batch,
    cancel_batch,
    format_apply_summary,
)

txns = parse_ofx(content)  # OfxTxn: fitid, posted_date, amount_cents, direction, memo
batch = create_batch(db, user_id, card, filename, content)
review = batch_review_context(db, batch)
summary = apply_batch(db, user_id, card, batch.id, choices)
```

| Ação | Quando | Efeito |
|------|--------|--------|
| `create` | Débito sem match | Compra `planned` no cartão + `ofx_fitid` |
| `match` | Débito com candidato (valor + data ±3d + memo) | Grava `ofx_fitid` no lançamento |
| `pay_invoice` | Crédito ≈ total de fatura aberta/fechada | `pay_invoice` + `ofx_fitid` na despesa bancária |
| `link_invoice_payment` | Crédito ≈ fatura já paga | Anexa `ofx_fitid` ao pagamento existente |
| `skip` | Só com confirmação explícita na revisão | No-op |
| `already_imported` | FITID já em `transactions` | No-op |
| `pending` | Crédito sem match automático | Exige escolha do usuário (não aplica sozinho) |

Cada linha (exceto já importada) exige seleção de **fatura** ao criar/conciliar/pagar.

## Schemas

```python
CreateCardInput(name, closing_day, due_day, settlement_account_name, institution?, credit_limit?)
UpdateCardInput(card_id?, card_name?, name?, institution?, credit_limit?, closing_day?, due_day?, settlement_account_name?)
DeleteCardInput(card_id?, card_name?)
TransactionCreate(..., ofx_fitid?)  # usado no apply create
```

## Assistente — argumentos

| Ferramenta | Identificação | Campos editáveis |
|------------|---------------|------------------|
| `create_card` | wizard pergunta tudo | name, institution, closing_day, due_day, credit_limit, settlement_account_name |
| `update_card` | `card_id` ou `card_name` | name, institution, credit_limit, closing_day, due_day, settlement_account_name |
| `delete_card` | `card_id` ou `card_name` | — |
| `pay_invoice` | `account_name` ou `invoice_id` | `from_account_name`, `payment_date?` |

Importação OFX **não** tem ferramenta de chat na v1 (somente UI).

## UI

- `/` — dashboard com seção **Cartões e faturas** (`summary.card_invoices`)
- `/accounts/cards` — hierarquia expansível: cartão → faturas → movimentos (`cards_with_nested_invoices` / `list_invoice_movements`)
- CRUD: `/accounts/cards/new`, `/accounts/cards/{id}/edit` (conta de liquidação obrigatória)
- **Pagar fatura** dentro da fatura expandida
- **Excluir fatura** — remove a fatura e compras do cartão ligadas; pagamento na conta (se pago) permanece
- **Importar OFX**: `/accounts/cards/{id}/ofx` → revisão → aplicar (`card_ofx_upload.html`, `card_ofx_review.html`)

## Reset de dados

```sql
DELETE FROM ofx_import_lines;
DELETE FROM ofx_import_batches;
DELETE FROM transactions;
DELETE FROM card_invoices;
DELETE FROM credit_cards;
```

(após transações, por causa de `invoice_id` / `card_id` / `ofx_fitid`)
