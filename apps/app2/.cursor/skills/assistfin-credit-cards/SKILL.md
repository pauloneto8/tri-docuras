---
name: assistfin-credit-cards
description: >-
  Cartões de crédito e faturas no AssistFin: entidade CreditCard separada de
  contas bancárias, limite, fechamento, vencimento, ciclo de fatura, liquidação,
  pagamento e importação OFX (revisão, conciliação, FITID). Use ao implementar
  cartão, fatura, fechamento, vencimento, limite disponível, CRUD de cartão,
  pagar fatura ou importar OFX.
paths: app/services/credit_cards.py, app/services/finance.py, app/services/card_wizard.py, app/services/ofx_card_import.py, app/models.py, app/services/pay_invoice_slots.py, app/templates/accounts.html, app/templates/card_form.html, app/templates/card_edit.html, app/templates/card_ofx_upload.html, app/templates/card_ofx_review.html, app/routers/pages.py, tests/test_credit_cards.py, tests/test_card_wizard.py, tests/test_update_card.py, tests/test_ofx_card_import.py
---

# AssistFin — Cartões e faturas

## Regras

- **Cartão ≠ conta bancária** — entidade `CreditCard` (`credit_cards`); contas são só `corrente`, `poupanca`, `carteira`.
- Cadastro exige `closing_day`, `due_day` e `settlement_account_name` (conta de liquidação padrão).
- Compra no cartão = `expense` com `card_id` + `invoice_id`; **não** altera saldo bancário.
- Pagar fatura = despesa na conta de débito (`pay_invoice`); marca fatura como `paid` — **não** duplica despesa da compra.
- Ciclo: compra após fechamento vai para a **próxima** fatura.
- Exclusão de cartão = `is_active=false` (soft delete); histórico de faturas e lançamentos preservado.
- **OFX** — importação com revisão; débitos criam/conciliam compras (`ofx_fitid`); créditos sugerem pagar/vincular fatura; estornos sem fatura = ignorar.

## Arquivos

| Arquivo | Papel |
|---------|--------|
| `app/services/credit_cards.py` | Ciclo, `ensure_invoices`, `pay_invoice`, limite, `cards_with_nested_invoices`, `list_invoice_movements` |
| `app/services/ofx_card_import.py` | Parse OFX, matching, lote de revisão, `apply_batch` |
| Templates | `accounts.html` (hierarquia), `card_form.html`, `card_edit.html`, `card_ofx_*.html` |
| `app/services/finance.py` | `create_card`, `update_card`, `deactivate_card`, `find_card` |
| `app/services/card_wizard.py` | Wizard do assistente para cadastro (`create_card`) |
| Migração `015` | `card_invoices`, `transactions.invoice_id` |
| Migração `016` | `credit_cards`, `transactions.card_id`, migração de legado |
| Migração `017` | `ofx_fitid`, `ofx_import_batches`, `ofx_import_lines` |
| `pay_invoice_slots.py` | Wizard do assistente para pagar fatura |

## Assistente

| Ferramenta | Uso |
|------------|-----|
| `create_card` | Cadastrar (wizard: apelido → instituição → fechamento → vencimento → limite → liquidação) |
| `update_card` | Editar cartão existente (confirmação obrigatória) |
| `delete_card` | Excluir cartão (desativação lógica; confirmação obrigatória) |
| `list_invoices` | Consultar faturas |
| `pay_invoice` | Pagar fatura (confirmação obrigatória) |

## UI

- `/` — dashboard com faturas (total a pagar, vencimento, limite)
- `/accounts` — contas bancárias (CRUD: `/accounts/new`, `/{id}/edit`)
- `/accounts/cards` — hierarquia expansível: cartão → faturas → movimentos (`cards_with_nested_invoices`); CRUD em `/accounts/cards/new` e `/{id}/edit`
- `POST /accounts/cards` — criar cartão; `POST /accounts/cards/{id}` — editar; desativar via delete
- `/accounts/cards/{id}/ofx` — upload OFX → revisão → aplicar (criar / conciliar / pagar fatura)
- `POST /accounts/invoices/{id}/pay` — pagar fatura (dentro da fatura expandida)
- Chat: após compra no cartão, `invoice_context_summary` via `enrich_register_result`

## Testes

- `tests/test_credit_cards.py` — domínio (ciclo, compra, pagamento)
- `tests/test_card_wizard.py` — wizard de cadastro
- `tests/test_update_card.py` — `update_card`, `deactivate_card`, rule-based
- `tests/test_runner_update_card.py` — confirmação no runner
- `tests/test_ofx_card_import.py` — parse, create/match, pay_invoice, idempotência FITID

## Referência

[reference.md](reference.md)
