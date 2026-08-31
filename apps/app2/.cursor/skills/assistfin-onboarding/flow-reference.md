# Fluxo de onboarding — referência

## Sequência HTTP

```
POST /login
  → login_user(session)
  → seed_defaults(categorias)
  → if not user.onboarding_completed → 303 /onboarding
  → else mark_login_prompt + 303 /

GET /onboarding
  → require_user
  → if completed → 303 /

POST /onboarding
  → validate_csrf_token
  → complete_onboarding(name, opening_balance, opening_balance_date)
  → mark_login_prompt
  → 303 /
```

## Modelo `User`

```python
onboarding_completed: bool = False  # migração 007
```

## Conta criada

```python
CreateAccountInput(
    name=name.strip(),
    account_type="carteira",
    opening_balance=opening_balance or "0",
    opening_balance_date=opening_balance_date,  # migração 008
)
```

## Saldo inicial com data

- `opening_balance_date` define quando o saldo inicial começa a contar
- Meses/dias anteriores à data não incluem o saldo inicial nos cálculos
- Assistente pode alterar via `update_account` com `opening_balance_date`

## Onboarding vs agente

| | Onboarding | Agente `create_account` |
|--|------------|-------------------------|
| Quando | Primeiro login | Qualquer momento |
| UI | Página dedicada | Wizard no chat |
| Tipo | Sempre carteira | Usuário escolhe |

## SQL útil

```sql
SELECT email, onboarding_completed FROM users;
SELECT name, opening_balance_cents, opening_balance_date
FROM accounts WHERE user_id = <id>;
```

## Reset de teste

Ver [docs/OPERATIONS.md](../../../docs/OPERATIONS.md) — `UPDATE users SET onboarding_completed = false`
