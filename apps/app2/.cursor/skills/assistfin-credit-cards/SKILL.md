---
name: assistfin-credit-cards
description: >-
  Cartões de crédito e faturas no AssistFin: entidade CreditCard separada de
  contas bancárias, limite, fechamento, vencimento, ciclo de fatura, liquidação
  e pagamento. Use ao implementar cartão, fatura, fechamento, vencimento, limite
  disponível, CRUD de cartão ou pagar fatura.
paths: app/services/credit_cards.py, app/services/finance.py, app/services/card_wizard.py, app/models.py, app/services/pay_invoice_slots.py, app/templates/accounts.html, app/routers/pages.py, tests/test_credit_cards.py, tests/test_card_wizard.py, tests/test_update_card.py
---

# AssistFin — Cartões e faturas

## Regras

- **Cartão ≠ conta bancária** — entidade `CreditCard` (`credit_cards`); contas são só `corrente`, `poupanca`, `carteira`.
- Cadastro exige `closing_day`, `due_day` e `settlement_account_name` (conta de liquidação padrão).
- Compra no cartão = `expense` com `card_id` + `invoice_id`; **não** altera saldo bancário.
- Pagar fatura = despesa na conta de débito (`pay_invoice`); marca fatura como `paid` — **não** duplica despesa da compra.
- Ciclo: compra após fechamento vai para a **próxima** fatura.
- Exclusão de cartão = `is_active=false` (soft delete); histórico de faturas e lançamentos preservado.

## Arquivos

| Arquivo | Papel |
|---------|--------|
| `app/services/credit_cards.py` | Ciclo, `ensure_invoices`, `pay_invoice`, limite, `format_credit_card` |
| `app/services/finance.py` | `create_card`, `update_card`, `deactivate_card`, `find_card` |
| `app/services/card_wizard.py` | Wizard do assistente para cadastro (`create_card`) |
| Migração `015` | `card_invoices`, `transactions.invoice_id` |
| Migração `016` | `credit_cards`, `transactions.card_id`, migração de legado |
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
- `/accounts` — contas bancárias
- `/accounts/cards` — mesma página `accounts.html` com `focus_cards=true` (cadastro e faturas)
- `POST /accounts/cards` — criar cartão
- `POST /accounts/invoices/{id}/pay` — pagar fatura

## Testes

- `tests/test_credit_cards.py` — domínio (ciclo, compra, pagamento)
- `tests/test_card_wizard.py` — wizard de cadastro
- `tests/test_update_card.py` — `update_card`, `deactivate_card`, rule-based
- `tests/test_runner_update_card.py` — confirmação no runner

## Referência

[reference.md](reference.md)
