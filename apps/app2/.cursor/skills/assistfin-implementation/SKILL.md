---
name: assistfin-implementation
description: >-
  Implementação e deploy do AssistFin: FastAPI, Docker, testes, migrações,
  segurança e convenções do repositório. Use ao criar features, corrigir bugs,
  rodar testes, fazer deploy em /opt/hosting ou alterar auth, CSRF e nginx.
paths: app/**, tests/**, alembic/**, Dockerfile, entrypoint.sh, README.md, AGENTS.md, docs/**, AGENTS.md, docs/**
---

# AssistFin — Implementação

Documentação completa: [README.md](../../README.md), [AGENTS.md](../../AGENTS.md), [docs/](../../docs/).

## Estrutura do projeto

```
app/
  main.py          # FastAPI, middleware, CSP, onboarding gate
  auth.py          # sessão, root, escopo, bcrypt
  models.py        # SQLAlchemy (transfer_group_id, status, datas de competência)
  schemas.py       # Pydantic, ToolCall, format_brl
  routers/         # pages (HTML), api (JSON), auth
  services/        # finance, wizards, transaction_slots, tools, intents, transfer_slots
  agent/           # runner, llm, groq, ollama, prompt
  security/        # csrf, rate_limit
  templates/       # Jinja2 + HTMX + agent partials
tests/             # pytest (rodar no container)
alembic/           # migrações 001–012
docs/              # ARCHITECTURE, OPERATIONS, SECURITY, CHANGELOG
```

## Convenções de código

- Escopo mínimo: corrigir só o necessário.
- Dinheiro sempre em centavos no banco; exibição com `format_brl()`.
- Textos de UI em português (pt-BR).
- Transferências nunca entram em receitas/despesas do período.
- Não commitar `.env`, chaves API ou `SECRET_KEY`.

## Deploy (produção)

```bash
cd /opt/hosting
docker compose build app2
docker compose up -d app2
docker compose exec -T app2 python -m pytest -q
```

- App: `/opt/hosting/apps/app2`
- DB: `hosting-app2-db`, Ollama: `hosting-ollama` (rede interna)
- Usuário do container: `appuser`

## Migrações

Automáticas no `entrypoint.sh`. Manual:

```bash
docker compose exec -T app2 alembic upgrade head
```

## Segurança (não regredir)

Ver [docs/SECURITY.md](../../docs/SECURITY.md). Resumo:

- `APP2_SECRET_KEY` obrigatória
- CSRF, rate-limit login, TrustedHost, CSP
- Ollama só em `app2_internal`
- OpenAPI desabilitado

## Reset de dados de teste

Ver [docs/OPERATIONS.md](../../docs/OPERATIONS.md) — preserva usuários, apaga movimentos/contas/categorias.

## Checklist de feature

1. Modelo + migração (se persistir)
2. `finance.py` + `schemas.py`
3. Agente: `ToolCall`, `tools.py`, `prompt.py` (se exposto ao chat)
4. UI (templates)
5. Testes
6. Rebuild + pytest

## Multiusuário

- Novos cadastros: `is_active=false` até admin aprovar
- Root: `APP2_ROOT_EMAILS`
- Onboarding: `onboarding_completed` + `/onboarding`
