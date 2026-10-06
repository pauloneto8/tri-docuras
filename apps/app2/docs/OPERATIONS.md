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

## Insight financeiro proativo (opcional, desligado por padrão)

Requer `APP2_GROQ_API_KEY` (já usada pelo agente) e
`APP2_ENABLE_AI_INSIGHTS=true` no `.env` do host, depois recriar o serviço
(`docker compose up -d app2`) — sem isso o comando abaixo não faz nada. Ver
`docs/ARCHITECTURE.md` §Inteligência proativa.

Gera/atualiza o insight do mês de quem está em `APP2_INSIGHTS_EMAILS` (vazio =
`APP2_ROOT_EMAILS`):

```bash
docker compose exec -T app2 python -m app.scripts.generate_insights
```

Cada usuário custa ~350 tokens de LLM por dia (medido em 2026-10-05: 254 de
prompt + 97 de resposta, com `reasoning_effort=low` — antes eram ~2.500, porque
o `gpt-oss` gastava o `max_tokens` inteiro raciocinando). Ainda assim o free tier
do Groq é de 200.000 tokens/dia **por modelo** e uma mensagem do agente v2 gasta
~12.000: insight para todo mundo registrado continua esgotando o orçamento e
derrubando o chat. Por isso a lista é explícita — quem não estiver nela não entra.

Agendado 1x/dia às 06:00 no crontab do root (log em
`/var/log/assistfin-insights.log`, rotacionado por `/etc/logrotate.d/assistfin`):

```
0 6 * * * cd /opt/hosting && docker compose exec -T app2 python -m app.scripts.generate_insights >> /var/log/assistfin-insights.log 2>&1
```

## Agente autônomo v2 (loop de ferramentas)

Ligado por `APP2_ENABLE_AGENT_V2=true` + `APP2_AGENT_V2_USERS=<ids>` (lista
separada por vírgula; só esses usuários usam o v2, o restante segue no legado).
Sem isso, tudo roda no motor antigo. Ver `docs/ARCHITECTURE.md` §Agente
autônomo v2 e a skill `.cursor/skills/assistfin-agent-v2/SKILL.md`.

Avaliação contra Groq real (não roda no cron):

```bash
docker compose exec -T app2 python -m app.scripts.agent_eval --dry-run  # só valida o YAML
docker compose exec -T app2 python -m app.scripts.agent_eval --mode both --delay 45
```

O free tier não roda os 83 casos de uma vez: `--offset`/`--limit` separam o
lote e o script para sozinho quando o orçamento diário do modelo acaba (os
casos não medidos não contam como falha). O `--delay` default é 45 s porque o
teto é 8.000 tokens/min e um caso do v2 gasta ~12.000. Relatórios em
`docs/eval/`.

### Telegram

1. Crie um bot no @BotFather e copie o token.
2. No `.env` do host: `APP2_TELEGRAM_BOT_TOKEN=<token>` e
   `APP2_TELEGRAM_WEBHOOK_SECRET=<string aleatória>`; `docker compose up -d app2`.
3. Registre o webhook (uma vez):
   ```bash
   docker compose exec -T app2 python -m app.scripts.set_telegram_webhook
   ```
   Confira com `... set_telegram_webhook --info` (ou `--delete` para remover).
4. O usuário abre `/channels` no AssistFin, copia o código e manda
   `/vincular <código>` para o bot. Depois é só conversar (texto ou áudio).

### WhatsApp (Meta Cloud API)

1. No app da Meta, obtenha `APP2_WHATSAPP_ACCESS_TOKEN`,
   `APP2_WHATSAPP_PHONE_NUMBER_ID`, `APP2_WHATSAPP_VERIFY_TOKEN` (qualquer
   string, usada no handshake) e `APP2_WHATSAPP_APP_SECRET`; recrie o serviço.
2. Configure a URL do webhook na Meta: `https://assistfin.com.br/whatsapp/webhook`
   com o mesmo verify token.
3. Mesmo fluxo de vínculo em `/channels`.

### Resumo proativo diário (cron)

`app/services/proactive.py` monta o texto em Python (contas a vencer em 3 dias,
previstos atrasados, orçamento > 80%, faturas fechando) e
`app/scripts/notify_channels.py` envia pelos vínculos. Sem vínculo, o comando é
no-op seguro. Agendado 1x/dia às 06:05 no crontab do root:

```
5 6 * * * cd /opt/hosting && docker compose exec -T app2 python -m app.scripts.notify_channels >> /var/log/assistfin-notify.log 2>&1
```

Conferir no dia seguinte: `tail /var/log/assistfin-notify.log` (esperado
`Resumos proativos enviados: N/N vínculos`).

## Fallback de NLU do agente via Claude (opcional, desligado por padrão)

Requer `APP2_ANTHROPIC_API_KEY` e `APP2_ENABLE_AI_NLU_FALLBACK=true` no `.env`
do host, depois recriar o serviço (`docker compose up -d app2`). Sem isso,
comportamento idêntico a hoje (Groq → parser por regra → "não consegui
entender"). Não tem comando de cron — roda automaticamente dentro do chat
quando as duas primeiras tentativas falham. Ver `docs/ARCHITECTURE.md`
§Inteligência proativa e `.cursor/plans/agente-inteligencia-proativa.md`.

## Orquestrador multi-etapas do agente (opcional, desligado por padrão)

Requer `APP2_ANTHROPIC_API_KEY` e `APP2_ENABLE_AI_ORCHESTRATOR=true` no `.env`
do host, depois recriar o serviço (`docker compose up -d app2`). Sem isso,
pedidos amplos ("revise meus gastos e sugira cortes") continuam caindo no
roteamento normal (Groq → regra → "não consegui entender") como hoje. Não tem
comando de cron — roda dentro do chat quando a mensagem parece um pedido
amplo (heurística em `looks_like_broad_request`). Usa `ANTHROPIC_MODEL_REASONING`
(padrão `claude-sonnet-5`) em vez do modelo rápido das Fases 2-3, e o SDK
oficial `anthropic` (Tool Runner) — única parte do agente que depende dele,
o resto continua em `httpx` puro. Ver `docs/ARCHITECTURE.md` §Inteligência
proativa e `.cursor/plans/agente-inteligencia-proativa.md` (Fase 5).

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

## Importação de extrato (cartão)

Em `/accounts/cards`, use **Importar extrato** no cartão:

1. Envie `.ofx` / `.qfx` / `.csv` / `.pdf` (texto selecionável) — limite na app **10 MB** (respeite também `client_max_body_size` do Nginx)
2. Revise cada linha:
   - **Criar** compra prevista no cartão
   - **Conciliar** com lançamento existente (mesmo valor, data ±3 dias, descrição parecida)
   - **Pagar fatura** / **vincular pagamento** (créditos com valor ≈ fatura)
   - **Ignorar** (estornos sem fatura correspondente)
3. Confirme — FITIDs ficam em `transactions.ofx_fitid` (reimportação é idempotente)

Lotes pendentes (`ofx_import_batches`) expiram em **24h**. Serviço: `app/services/ofx_card_import.py`. Testes: `tests/test_ofx_card_import.py`.

## Importação de extrato (conta bancária)

Em `/accounts`, use **Importar extrato** na conta:

1. Envie `.ofx` / `.qfx` / `.csv` / `.pdf` (máx. 10 MB); Flash: `flash_extrato_*.csv`
2. Revise: débitos → despesas, créditos → receitas; criar ou conciliar; categoria opcional (memorizada)
3. Confirme — lançamentos entram como `actual` na data do extrato e alteram o saldo; FITID em `transactions.ofx_fitid`

### Formatos CSV / PDF / Flash

| Formato | Notas |
|--------|--------|
| **CSV genérico** | Delimitador `;` / `,` / TAB; preâmbulo do banco ok; colunas inferidas (data, valor ou débito/crédito, descrição); sem ID → FITID sintético estável |
| **Flash** | Arquivos `flash_extrato_*.csv` (export do app): TAB, valores `-R$ x,xx` (NBSP), colunas Data/Hora/Movimentação/Valor/Tipo/Saldo — **saldo ignorado**; sinal define despesa/receita |
| **PDF** | Texto selecionável via `pdfplumber`; linhas com valor + saldo usam o **valor do lançamento** (não o saldo); PDFs só imagem **não** suportados |

Serviço: `statement_parse.py` + `ofx_account_import.py` / `ofx_card_import.py`. Testes: `tests/test_statement_parse.py`, `tests/test_ofx_account_import.py`.

## Filtros da tela Movimentos

Em `/transactions`:

| Filtro | Query | Padrão |
|--------|-------|--------|
| Período | `period` (`day`\|`week`\|`month`) + `ref_date` | mês / hoje |
| Conta | `account_id` | todas |
| Cartão | `card_id` | todos (extrato omite compras de cartão até filtrar) |
| Categoria | `category_id` | todas |
| Tipo | `type` (`expense`\|`income`\|`transfer`\|`all`) | todos |

O conjunto aplicado (incluindo período) fica na **sessão** (`transactions_list_filter`) ao filtrar ou navegar. Voltar pelo menu `/transactions` restaura o último filtro. **Limpar** (`/transactions?clear=1`) apaga a sessão e volta ao padrão.

## Testes

A suíte cria usuários e transações de teste. **Rodar contra o
`hosting-app2-db` enche o banco de produção de lixo** (108 usuários
`@test.com` foram apagados em 2026-10-05 por causa disso) e o cron de insights
passa a tentar gerar insight para cada um. Use um Postgres descartável:

```bash
cd /opt/hosting
docker run -d --name app2-test-db --network app2_internal \
  -e POSTGRES_USER=app2 -e POSTGRES_PASSWORD=app2 -e POSTGRES_DB=app2 \
  postgres:16-alpine
# espera o banco responder
until docker exec app2-test-db pg_isready -U app2 -d app2; do sleep 1; done

TEST_DB="postgresql://app2:app2@app2-test-db:5432/app2"
docker compose run --rm --no-deps -T -e DATABASE_URL=$TEST_DB -e DB_HOST=app2-test-db \
  -v "$PWD/apps/app2:/app" --entrypoint sh app2 -c "alembic upgrade head"
docker compose run --rm --no-deps -T -e DATABASE_URL=$TEST_DB -e DB_HOST=app2-test-db \
  -v "$PWD/apps/app2:/app" --entrypoint python app2 -m pytest -q -p no:cacheprovider

# no fim
docker rm -f app2-test-db
```

Só para area específica, acrescente `tests/test_arquivo.py -q`.

Se precisar rodar no container de produção mesmo assim (ex.: depurar algo que
só acontece lá), limpe depois — a receita está em
[Zerar dados de teste](#zerar-dados-de-teste-manter-usuários) e, para os
usuários, `DELETE FROM users WHERE email LIKE '%@test.com'` depois de remover
transações, contas e categorias filhas (muitas FKs do schema não têm
`ON DELETE CASCADE`).

```bash
# Área específica (mesmo Postgres descartável acima)
docker compose exec -T app2 python -m pytest tests/test_transfers.py -q
docker compose exec -T app2 python -m pytest tests/test_update_transfer.py -q
docker compose exec -T app2 python -m pytest tests/test_update_transfer.py -q
docker compose exec -T app2 python -m pytest tests/test_summary.py -q
docker compose exec -T app2 python -m pytest tests/test_planned_transactions.py -q
docker compose exec -T app2 python -m pytest tests/test_recurrence.py -q
docker compose exec -T app2 python -m pytest tests/test_installments.py -q
docker compose exec -T app2 python -m pytest tests/test_credit_cards.py -q
docker compose exec -T app2 python -m pytest tests/test_ofx_card_import.py -q
docker compose exec -T app2 python -m pytest tests/test_ofx_account_import.py -q
docker compose exec -T app2 python -m pytest tests/test_statement_parse.py -q
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

O endpoint público é `/api/health` (o `/health` exige sessão e devolve 303 para
o login):

```bash
curl -s https://assistfin.com.br/api/health
# {"status":"ok"}
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
