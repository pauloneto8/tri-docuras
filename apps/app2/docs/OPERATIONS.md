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

## Backup e restauração (admin)

Na tela `/admin` (usuário root):

1. **Criar backup agora** — gera `assistfin_YYYYMMDD_HHMMSS.dump` (formato custom `pg_dump -Fc`)
2. **Baixar** / **Excluir** arquivos listados
3. **Restaurar** — digite exatamente `RESTAURAR` e confirme. O serviço encerra outras conexões, recria o schema `public`, aplica o dump com `pg_restore` e em seguida roda `alembic upgrade head` (para dumps antigos ganharem tabelas novas, ex. OFX).

Arquivos ficam no volume Docker `app2_backups` (`/app/data/backups` no container). Mantém os últimos 20 dumps.

Via CLI (equivalente):

```bash
docker compose exec -T app2-db pg_dump -U app2 -d app2 -Fc -f /tmp/manual.dump
# ou pela UI em /admin
```

## Importação OFX de cartão

Em `/accounts/cards`, use **Importar OFX** no cartão:

1. Envie o arquivo `.ofx` / `.qfx` / `.csv` do cartão — limite na app **5 MB** (respeite também `client_max_body_size` do Nginx)
2. Revise cada linha:
   - **Criar** compra prevista no cartão
   - **Conciliar** com lançamento existente (mesmo valor, data ±3 dias, descrição parecida)
   - **Pagar fatura** / **vincular pagamento** (créditos OFX com valor ≈ fatura)
   - **Ignorar** (estornos sem fatura correspondente)
3. Confirme — FITIDs ficam em `transactions.ofx_fitid` (reimportação é idempotente)

Lotes pendentes (`ofx_import_batches`) expiram em **24h**. Serviço: `app/services/ofx_card_import.py`. Testes: `tests/test_ofx_card_import.py`.

## Importação OFX de conta bancária

Em `/accounts`, use **Importar OFX** na conta:

1. Envie o extrato `.ofx` / `.qfx` / `.csv` (máx. 5 MB)
2. Revise: débitos → despesas, créditos → receitas; criar ou conciliar; categoria opcional (memorizada)
3. Confirme — lançamentos entram como `actual` na data do extrato e alteram o saldo; FITID em `transactions.ofx_fitid`

CSV esperado (`;` ou `,`): o arquivo pode vir no formato exportado pelo banco.
O parser analisa o conteúdo e identifica sozinho data, valor (ou débito/crédito) e descrição —
não exige nomes fixos de coluna. Sem identificador, gera um FITID estável.

Serviço: `app/services/ofx_account_import.py` + `statement_parse.py`. Testes: `tests/test_ofx_account_import.py`, `tests/test_statement_parse.py`.

## Testes

```bash
# Suite completa
docker compose exec -T app2 python -m pytest -q

# Área específica
docker compose exec -T app2 python -m pytest tests/test_transfers.py -q
docker compose exec -T app2 python -m pytest tests/test_update_transfer.py -q
docker compose exec -T app2 python -m pytest tests/test_summary.py -q
docker compose exec -T app2 python -m pytest tests/test_planned_transactions.py -q
docker compose exec -T app2 python -m pytest tests/test_recurrence.py -q
docker compose exec -T app2 python -m pytest tests/test_installments.py -q
docker compose exec -T app2 python -m pytest tests/test_credit_cards.py -q
docker compose exec -T app2 python -m pytest tests/test_ofx_card_import.py -q
docker compose exec -T app2 python -m pytest tests/test_ofx_account_import.py -q
docker compose exec -T app2 python -m pytest tests/test_realize_planned_wizard.py -q
docker compose exec -T app2 python -m pytest tests/test_multi_movements.py -q
docker compose exec -T app2 python -m pytest tests/test_chat_format.py -q
docker compose exec -T app2 python -m pytest tests/test_tools.py -q
```

## Zerar dados de teste (manter usuários)

Remove movimentos, contas, categorias, conversas, regras de recorrência e reseta onboarding:

```bash
cd /opt/hosting
docker compose exec -T app2-db psql -U "$(grep APP2_DB_USER .env | cut -d= -f2)" \
  -d "$(grep APP2_DB_NAME .env | cut -d= -f2)" -c "
DELETE FROM conversation_messages;
DELETE FROM conversations;
DELETE FROM ofx_import_lines;
DELETE FROM ofx_import_batches;
DELETE FROM ofx_category_memory;
DELETE FROM transactions;
DELETE FROM card_invoices;
DELETE FROM installment_plans;
DELETE FROM recurring_rules;
DELETE FROM budgets;
DELETE FROM credit_cards;
DELETE FROM accounts;
DELETE FROM categories;
UPDATE users SET onboarding_completed = false;
"
```

Usuários e senhas são preservados. Após o reset, faça **logout e login** se a sessão ou o onboarding parecerem inconsistentes.

O que é removido: movimentos, lotes OFX, cartões, faturas, planos de parcelas, regras de recorrência, contas, categorias, orçamentos, conversas do agente. O que permanece: usuários, aprovações e credenciais.

### Zerar tudo (incluindo usuários)

Trunca todas as tabelas de dados e reinicia IDs; mantém `alembic_version`:

```bash
cd /opt/hosting
docker compose exec -T app2 python - <<'PY'
from sqlalchemy import create_engine, text, inspect
from app.config import settings

engine = create_engine(settings.database_url)
tables = [t for t in inspect(engine).get_table_names() if t != "alembic_version"]
with engine.begin() as conn:
    quoted = ", ".join(f'"{t}"' for t in tables)
    conn.execute(text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"))
print("ok", tables)
PY
```

Depois disso é necessário **registrar / aprovar** usuários de novo (banco vazio).

### Zerar dados de um único usuário

Substitua `USER_ID` pelo `id` em `SELECT id, email FROM users`:

```bash
cd /opt/hosting
docker compose exec -T app2-db psql -U app2 -d app2 -c "
BEGIN;
DELETE FROM conversation_messages WHERE user_id = USER_ID;
DELETE FROM conversations WHERE user_id = USER_ID;
DELETE FROM transactions WHERE user_id = USER_ID;
DELETE FROM card_invoices WHERE user_id = USER_ID;
DELETE FROM installment_plans WHERE user_id = USER_ID;
DELETE FROM recurring_rules WHERE user_id = USER_ID;
DELETE FROM budgets WHERE user_id = USER_ID;
DELETE FROM credit_cards WHERE user_id = USER_ID;
DELETE FROM accounts WHERE user_id = USER_ID;
DELETE FROM categories WHERE user_id = USER_ID;
UPDATE users SET onboarding_completed = false WHERE id = USER_ID;
COMMIT;
"
```

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

## Groq

O assistente usa **apenas** Groq (`APP2_GROQ_API_KEY` / `APP2_GROQ_MODEL`). Sem chave ou com rate limit (429), a intenção cai no fallback de regras (`try_rule_based_parse`).

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
| Chat timeout | Nginx `/agent/` timeout 120s; verificar Groq (chave/rate limit) |
| Sessão/onboarding inconsistente | Logout + login após reset de DB |
| Lista de Movimentos confusa após realizar previsto | Deploy recente separa “A realizar” e “Extrato”; previsto liquidado some da lista (normal) |
| Wizard criou várias despesas ao digitar data (`10/08/2026`) | Corrigido em 2026-08-31 — rebuild `app2`; ver `CHANGELOG.md` |
| Responder "não" no slot de recorrência cancelou o wizard | Corrigido em 2026-08-31 — rebuild `app2` |
| `*negrito*` aparece literal no chat | Filtro `chat_md` (2026-09-02); rebuild `app2` |
| Corrigir transferência criou outro lançamento | Usar `update_transfer` (2026-09-02); rebuild `app2` |
| Previstos fixos não aparecem à frente | Acesse Dashboard ou Movimentos (`ensure_recurring_horizon`); verifique regra ativa |
| 502 | `docker compose ps app2` |
