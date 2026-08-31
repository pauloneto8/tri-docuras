# Operações — AssistFin

## Deploy

```bash
cd /opt/hosting
docker compose build app2
docker compose up -d app2
docker compose exec -T app2 python -m pytest -q
```

Após alterar template Nginx ou domínio:

```bash
./scripts/reload-nginx.sh
```

## Migrações

Aplicadas automaticamente no startup (`entrypoint.sh`). Manual:

```bash
docker compose exec -T app2 alembic upgrade head
docker compose exec -T app2 alembic current
```

Nova revisão:

```bash
docker compose exec -T app2 alembic revision -m "descricao" --autogenerate
```

## Testes

```bash
# Suite completa
docker compose exec -T app2 python -m pytest -q

# Área específica
docker compose exec -T app2 python -m pytest tests/test_transfers.py -q
docker compose exec -T app2 python -m pytest tests/test_summary.py -q
docker compose exec -T app2 python -m pytest tests/test_planned_transactions.py -q
docker compose exec -T app2 python -m pytest tests/test_multi_movements.py -q
```

## Zerar dados de teste (manter usuários)

Remove movimentos, contas, categorias, conversas e reseta onboarding:

```bash
cd /opt/hosting
docker compose exec -T app2-db psql -U "$(grep APP2_DB_USER .env | cut -d= -f2)" \
  -d "$(grep APP2_DB_NAME .env | cut -d= -f2)" -c "
DELETE FROM conversation_messages;
DELETE FROM conversations;
DELETE FROM transactions;
DELETE FROM budgets;
DELETE FROM accounts;
DELETE FROM categories;
UPDATE users SET onboarding_completed = false;
"
```

Usuários e senhas são preservados. Após o reset, faça **logout e login** se a sessão ou o onboarding parecerem inconsistentes.

O que é removido: movimentos, contas, categorias, orçamentos, conversas do agente. O que permanece: usuários, aprovações e credenciais.

## Logs

```bash
docker compose logs -f app2
docker compose logs -f app2-db
docker compose logs -f nginx
```

## Debug do agente

```sql
SELECT role, content, tool_used, source, created_at
FROM conversation_messages
ORDER BY created_at DESC
LIMIT 30;
```

## Ollama

```bash
docker compose exec ollama ollama pull qwen3:1.7b
docker compose exec ollama ollama list
```

## Health check

```bash
curl -s http://localhost/api/health
# ou via domínio configurado
```

## Troubleshooting

| Problema | Ação |
|----------|------|
| Mudança não aparece | `docker compose build --no-cache app2 && docker compose up -d app2` |
| Erro de migração | `alembic current` + logs do container |
| Chat timeout | Nginx `/agent/` timeout 120s; verificar Groq/Ollama |
| Sessão/onboarding inconsistente | Logout + login após reset de DB |
| Lista de Movimentos confusa após realizar previsto | Deploy recente separa “A realizar” e “Extrato”; previsto liquidado some da lista (normal) |
| Wizard criou várias despesas ao digitar data (`10/08/2026`) | Corrigido em 2026-08-31 — rebuild `app2`; ver `CHANGELOG.md` |
| 502 | `docker compose ps app2` |
