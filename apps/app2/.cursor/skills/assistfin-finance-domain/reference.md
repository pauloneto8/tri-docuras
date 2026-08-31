# Referência financeira — AssistFin

## Funções principais (`app/services/finance.py`)

| Função | Uso |
|--------|-----|
| `resolve_transaction_dates(status, …)` | Normaliza competência, vencimento, pagamento e `transaction_date` |
| `get_summary(db, user_id, SummaryInput)` | Receitas/despesas/resultado do período + saldos + previstos/projeção |
| `account_balances(db, user_id, as_of=date)` | Saldos por conta em uma data (só `actual`) |
| `register_expense` / `register_income` | Lançamentos (planned ou actual) |
| `realize_planned` | Converter previsão em realizado |
| `register_transfer` | Par transfer_out + transfer_in |
| `update_transaction` / `delete_transaction` | Editar/excluir (par em transferências) |
| `update_account` | Editar conta (saldo inicial, data, apelido…) |
| `create_account` / `create_category` | Cadastros |
| `complete_onboarding` | Primeira conta |
| `list_transactions` | Movimentos |
| `list_user_categories` | Categorias do usuário |
| `get_budget_status` | Orçamentos vs gasto |
| `_account_balance_at` | Saldo de uma conta em uma data |

## Ferramentas do agente (`ToolCall`)

| Ferramenta | Confirmação |
|------------|-------------|
| `register_expense`, `register_income`, `register_transfer` | Sim |
| `realize_planned` | Sim |
| `update_transaction`, `delete_transaction`, `update_account` | Sim |
| `create_account`, `create_category` | Sim (wizard) |
| `list_*`, `get_summary`, `get_budget_status`, `categorize` | Não |

## Migrações relevantes

| Revisão | Conteúdo |
|---------|----------|
| 003 | `opening_balance_cents`, campos bancários |
| 007 | `onboarding_completed` |
| 008 | `opening_balance_date` |
| 009 | Normalização nomes de categorias |
| 010 | `transfer_group_id`, `counterparty_account_id`, tipos transfer |
| 011 | `status` (planned/actual), `source_planned_id` |
| 012 | `competence_date`, `due_date`, `payment_date` |

## Formatação BRL

```python
from app.schemas import format_brl, decimal_to_cents
format_brl(123456)  # "1.234,56"
decimal_to_cents("45,90")  # 4590
```
