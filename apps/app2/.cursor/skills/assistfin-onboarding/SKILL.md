---
name: assistfin-onboarding
description: >-
  Onboarding do AssistFin: primeira conta, saldo inicial, data do saldo inicial,
  middleware de redirecionamento, sessão e fluxo pós-login. Use ao alterar
  onboarding.html, complete_onboarding, login, conta principal ou welcome do agente.
paths: app/routers/auth.py, app/main.py, app/auth.py, app/services/finance.py, app/templates/onboarding.html, app/templates/login.html, alembic/versions/007_user_onboarding.py, alembic/versions/008_account_opening_balance_date.py, tests/test_onboarding.py
---

# AssistFin — Onboarding

## Objetivo

No **primeiro acesso** após login aprovado, o usuário configura a **conta principal**: apelido, saldo inicial (opcional) e **data do saldo inicial**.

## Fluxo

```
register → login (se is_active) → /onboarding → POST cria conta → dashboard
                                      ↓
                            mark_login_prompt → agente pergunta despesa/receita
```

## Arquivos-chave

| Arquivo | Papel |
|---------|-------|
| `finance.complete_onboarding()` | Conta `carteira` + `onboarding_completed=true` |
| `auth.py` login | Redirect `/onboarding` se incompleto |
| `main.py` middleware | Bloqueia rotas até onboarding |
| `transaction_wizard.mark_login_prompt()` | Abre assistente no dashboard |

## Campos do onboarding

- `name` — apelido da conta (mín. 2 caracteres)
- `opening_balance` — opcional, default 0
- `opening_balance_date` — data em que o saldo inicial passa a valer

## Middleware (`main.py`)

- `onboarding_completed` false → redirect `/onboarding` (HTML) ou 403 (API)
- Exceções: `/onboarding`, `/logout`, `/login`, `/register`, `/static`, `/api/health`

## Sessão

- `onboarding_completed` deve espelhar DB após login
- `prompt_transaction_on_login` — flag para welcome do agente
- Após reset de DB: **logout + login** para sincronizar sessão

## Pós-onboarding

1. Redirect `/`
2. `GET /agent/welcome` se `prompt_transaction_on_login`
3. Chips Despesa/Receita no assistente

## Armadilhas

- `seed_defaults` cria categorias, **não** conta
- Onboarding ≠ wizard `create_account` do agente
- `get_primary_account()` = conta mais antiga (`created_at` ASC)

## Testes

```bash
docker compose exec -T app2 python -m pytest tests/test_onboarding.py -q
```

## Referência

[flow-reference.md](flow-reference.md)
