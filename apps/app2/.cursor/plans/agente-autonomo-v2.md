# Plano: Agente autônomo do AssistFin (v2) — briefing para implementação

**Status:** código das Fases 0-6 implementado (2026-10-04); migrações `022`/`023` aplicadas; suíte com 446 testes verde. `ENABLE_AGENT_V2` ligado só para `AGENT_V2_USERS=1`.
**Pendente (operacional):** tokens e webhook do Telegram; credenciais do WhatsApp na Meta; cron de `notify_channels`/`generate_insights` (`ENABLE_AI_INSIGHTS` ainda `false`); rodar `agent_eval` contra o Groq real (meta ≥ 90%, v2 ≥ legado); testes manuais da seção Verificação; tratar respostas 429 do Groq vistas no log.
**Workspace:** `/opt/hosting/apps/app2`. Responder ao usuário em **português**.

## Antes de começar (notas para o agente implementador)

- Ler: `AGENTS.md`, `.cursor/skills/assistfin-ai-agent/SKILL.md`, `.cursor/skills/assistfin-agent-tests/SKILL.md`, `.cursor/skills/ai-agent-design-patterns/SKILL.md`, `.cursor/skills/assistfin-finance-domain/SKILL.md`, e o plano anterior `.cursor/plans/agente-inteligencia-proativa.md` (Fases 1-5 já implementadas; Claude desligado e **sem** `APP2_ANTHROPIC_API_KEY` no `.env`).
- **Os testes usam o Postgres de produção** (`settings.database_url`, criam usuários `*@example.com` aleatórios). Para rodar sem rebuild/deploy do app, use um container descartável com o código montado:
  ```bash
  cd /opt/hosting
  docker compose run --rm --no-deps -T -v "$PWD/apps/app2:/app" --entrypoint python app2 -m pytest -q -p no:cacheprovider
  ```
- **Linha de base (2026-10-03, com `-x`):** 267 passaram e 1 falhou antes de parar: `tests/test_root.py::test_root_personal_scope_excludes_other_users`. Essa falha **já existia** e não tem relação com este plano. Rode a suíte completa sem `-x` antes de mexer para registrar a linha de base inteira.
- **Antes de aplicar a migração 022 no banco real**, faça um backup (`app/services/db_backup.py` / painel `/admin`, ou `pg_dump` no container `hosting-app2-db`).
- Deploy só ao final de cada fase validada: `cd /opt/hosting && docker compose build app2 && docker compose up -d app2`.
- Segredos (tokens Telegram/WhatsApp) **só** no `/opt/hosting/.env`; nunca no código.

**Workspace:** `/opt/hosting/apps/app2` (FastAPI + Postgres, container `hosting-app2`)
**Decisões do usuário (2026-10-03):** cérebro **só Groq** (`openai/gpt-oss-120b`); **toda escrita confirmada** (um clique, inclusive lote); canais **chat web + Telegram + WhatsApp**.

## Contexto

Hoje o agente é uma cascata frágil: ~10 wizards de slots (regex) → atalhos de regra → Groq escolhendo **uma** ferramenta via JSON em texto (`app/agent/groq.py`, `prompt.py`) → fallback de regras. Ele não encadeia ações (não consegue "procurar o lançamento do mercado de ontem e mudar para 80"), não enxerga a conversa de verdade (só 4 mensagens como texto em `context.py`), e qualquer frase fora dos padrões cai em "não entendi". As partes Claude (insight, fallback, orquestrador) estão desligadas e sem chave.

Objetivo: trocar o "roteador de 1 ferramenta" por um **loop agêntico** (o modelo raciocina, chama várias ferramentas de leitura, decide, propõe escritas), mantendo o que já é bom: `finance.py` como única fonte de cálculo, `execute_tool` como executor, confirmação obrigatória, isolamento por `user_id`.

## Arquitetura alvo

```
mensagem (web | telegram | whatsapp)
  → AgentSession (estado no Postgres, por usuário+canal)
  → agent_loop (Groq, tools nativas OpenAI-compat, até 8 iterações)
       ├─ tool de LEITURA → executa já, devolve JSON ao modelo
       ├─ tool de ESCRITA → valida + resolve ids + gera prévia, NÃO grava → acumula em "plano pendente"
       └─ resposta final (texto) ou pergunta do que falta
  → se plano pendente: cartão Confirmar/Cancelar (web: HTMX; Telegram: inline keyboard; WhatsApp: botões)
  → confirmar: executa lote via execute_tool numa transação → resultado volta ao modelo p/ mensagem final
  → falha do Groq/timeout → cai no pipeline legado (process_message atual), sem perda de função
```

## Fases

### Fase 0 — Base de avaliação (antes de mexer)
- `tests/agent_eval/cases.yaml`: ~80 frases reais em pt-BR (lançar simples/cartão/parcelado/fixo, vários numa frase, editar, excluir, transferir, pagar fatura, realizar previsto, perguntas analíticas, gírias/erros de digitação). Cada caso: mensagem + estado inicial + ferramentas/argumentos esperados.
- `app/scripts/agent_eval.py`: roda os casos contra o Groq real (só manual, `GROQ_API_KEY`), mede acerto de ferramenta/argumentos, compara **legado vs v2**. É o critério de "ficou mais inteligente".

### Fase 1 — Toolkit tipado (registry único de ferramentas)
Novo `app/agent/toolkit.py`: cada ferramenta = `name`, `description` rica em pt-BR, `parameters` (JSON Schema gerado de modelos Pydantic de `app/schemas.py` via `model_json_schema()`), `kind` (`read`/`write`), handler.
- **Escrita** (reaproveita `execute_tool` em `app/services/tools.py:792` e `WRITE_TOOLS` de `runner.py`): `register_expense`, `register_income` (incl. parcelado/fixo/cartão), `register_transfer`, `realize_planned`, `update_transaction` (+ `installment_scope`), `update_transfer`, `delete_transaction`, `pay_invoice`, contas/cartões/categorias, orçamento.
- **Leitura existente**: `list_transactions`, `list_accounts`, `list_categories`, `get_summary`, `get_budget_status`, `list_invoices`, `categorize`.
- **Leitura nova** (funções finas sobre `finance.py`/`credit_cards.py`/`recurrence.py`/`installments.py`, sem cálculo no LLM):
  - `search_transactions(text?, amount?, date_from?, date_to?, account?, card?, category?, status?)` → retorna **ids** + resumo; usa `services/fuzzy_match.py`. Obrigatória antes de editar/excluir.
  - `get_balances(as_of?)`, `get_cashflow_projection(days)` (previstos + faturas), `compare_periods(a, b)`, `spending_breakdown(period, group_by=category|account|card|description)`, `list_upcoming_bills(days)`, `list_recurring_and_installments()`, `get_invoice_detail(card, month)`.
- Resolução de nomes→ids e parse de valor/data em **Python** (`parse_amount`, `parse_user_date`, `resolve_movement_accounts`, `lookup_description_preference`). Erro de validação vira resultado da ferramenta (`{"error": "...", "hint": "..."}`) para o modelo se autocorrigir.

### Fase 2 — Loop agêntico com Groq
Novo `app/agent/brain.py` (+ `app/agent/groq.py` ganha `chat_with_tools(messages, tools)`):
- Chat Completions do Groq com `tools`, `tool_choice="auto"`, `parallel_tool_calls`, `temperature` baixa; `reasoning_effort` do gpt-oss (`medium`, `high` para análises), timeout e retry com backoff (limites de taxa do Groq).
- Limite: 8 iterações / ~30 s; deduplicação de chamadas idênticas.
- **System prompt dinâmico** (`app/agent/prompt_v2.py`): data/hora `America/Recife` (`app/timezone.py`), contas/cartões/categorias do usuário (reaproveitar blocos de `build_intent_context`), preferências aprendidas, regras do domínio do `AGENTS.md` (centavos, transferência não é despesa, competência × vencimento × pagamento, compra no cartão vai para fatura), política: *pergunte só o que falta; padrões: realizado, hoje, conta/cartão inferidos; para editar/excluir sempre `search_transactions` primeiro; se houver mais de 1 candidato, pergunte mostrando as opções.*
- **Escritas viram plano pendente**: o handler valida e devolve ao modelo `{"status":"pending_confirmation","preview":...}` — o modelo nunca "acha" que gravou. Prévia usa `format_pending_confirmation`.
- **Anti-alucinação**: reaproveitar `_MONEY_RE` de `app/agent/orchestrator.py` — todo `R$` na resposta final tem de ter saído de uma ferramenta; se não, 1 retentativa pedindo correção; persistindo, resposta genérica.
- **Memória de conversa real**: últimas ~12 trocas (inclusive tool calls resumidas) vindas de `conversation_messages` (gravar `metadata.tool_calls`), em vez das 4 linhas de texto atuais.
- Gravar `source="agent-v2"` e métricas (iterações, ferramentas, latência, tokens) em `conversation_messages.metadata`.

### Fase 3 — Estado por canal + confirmação em lote
- Migração `alembic/versions/022_agent_sessions.py`: tabela `agent_sessions` (`user_id`, `channel`, `external_chat_id`, `pending_plan` JSONB, `updated_at`) — necessária porque Telegram/WhatsApp não têm sessão Starlette.
- `app/agent/confirm.py`: `confirm_plan()` executa cada ação via `execute_tool` numa única transação (tudo ou nada), limpa o plano, chama o modelo 1 vez para resumir o resultado (com `context_summary`/`enrich_register_result` existentes); `cancel_plan()`; plano expira em 30 min.
- Ganchos já existentes preservados: `offer_description_preference_from_result` após lançamento.
- Web: `/agent/chat` em `app/routers/pages.py` passa a chamar `brain.run()` quando `ENABLE_AGENT_V2`; confirmação usa id do plano (não mais o JSON inteiro no form → também fecha o vetor de adulteração de `pending_action`). Partials `agent_confirm_actions.html` listam N ações.
- Feature flag `ENABLE_AGENT_V2` + `AGENT_V2_USERS` (começar só pelo seu usuário) em `app/config.py` e `docker-compose.yml` (`APP2_ENABLE_AGENT_V2`). Legado intacto como fallback e rollback.

### Fase 4 — Telegram
- `app/routers/telegram.py`: `POST /telegram/webhook/{secret}` (verifica `X-Telegram-Bot-Api-Secret-Token`), isento de CSRF (`app/security/csrf.py`), com rate limit (`app/security/rate_limit.py`).
- Vínculo de conta: página "Conectar Telegram" gera código de 6 dígitos (10 min); usuário manda `/vincular 123456` ao bot → tabela `user_channel_links` (mesma migração 022). Mensagem de chat não vinculado não acessa nada.
- Mensagens → `brain.run(channel="telegram")`; plano pendente → botões inline **Confirmar / Cancelar** (`callback_query`).
- **Áudio**: mensagem de voz → transcrição via Groq Whisper (`whisper-large-v3-turbo`, mesma chave) → loop normal. "Gastei 42 no posto ontem no Nubank" falado.
- Envio via `httpx` (padrão de `groq.py`), sem nova dependência. Env: `APP2_TELEGRAM_BOT_TOKEN`, `APP2_TELEGRAM_WEBHOOK_SECRET`. Nginx já roteia `assistfin.com.br` → app2, nada a mudar.

### Fase 5 — WhatsApp (Meta Cloud API)
- Mesmo desenho do Telegram em `app/routers/whatsapp.py` (verificação `hub.challenge`, assinatura `X-Hub-Signature-256`), botões interativos para confirmar, áudio via Whisper.
- Reaproveitar o modelo de configuração já usado no app1 (`apps/app1/api/lib/whatsapp_notify.dart`: `ACCESS_TOKEN`, `PHONE_NUMBER_ID`). Requer número/app verificado na Meta (passo manual seu); fica depois do Telegram.

### Fase 6 — Proatividade
- `app/services/insights.py` passa a usar Groq (provider único) em vez de Claude, mantendo a validação de valores existente.
- Job diário (cron do host, padrão de `docs/OPERATIONS.md` / `app/scripts/generate_insights.py`): por usuário vinculado, envia no Telegram/WhatsApp contas a vencer em 3 dias, previstos atrasados, orçamento > 80%, fatura fechando. Tudo calculado em Python; LLM só redige.
- Comandos rápidos: "resumo do mês", "quanto posso gastar até o fim do mês?" (projeção via `get_cashflow_projection`).

## Banco de dados e vetores (verificado em 2026-10-03)
- Já usa **PostgreSQL 16.15** (`postgres:16-alpine`, container `hosting-app2-db`), 587 transações.
- Extensões **já instaladas**: `pg_trgm` e `unaccent`. **Não há pgvector** (a imagem alpine nem oferece a extensão) e nenhum código de embedding no app.
- Decisão: **não usar vetores agora**. O Groq não oferece API de embeddings (exigiria outro provedor ou modelo local), e o volume de uma pessoa cabe em busca SQL. `search_transactions` usa `unaccent` + `pg_trgm` (`similarity()`/`%`) + filtros de valor/data — tolera erro de digitação ("ifod", "mercadu") sem infraestrutura nova. Migração 022 cria índice GIN trigram em `lower(unaccent(description))`.
- Se um dia quiser busca semântica ("gastos com lazer" sem categoria): trocar a imagem por `pgvector/pgvector:pg16` (mesma versão major, volume compatível), `CREATE EXTENSION vector`, embeddings locais (ex.: `fastembed`) — fica fora deste plano.

## Pesquisa GitHub — o que usar e o que não
- **Jarvis** (ex.: JohannsenLum/jarvis, ethanplusai/jarvis, PersonalJarvis): são assistentes pessoais que rodam *em cima* do Claude Code no desktop/Mac, dependem da assinatura Claude e não entram num backend FastAPI multiusuário. **Não instalar** — o "Jarvis" aqui é o próprio loop + Telegram/WhatsApp.
- **anthropics/skills**, **ComposioHQ/awesome-claude-skills**, **alirezarezvani/claude-skills**: úteis como *referência de escrita de skill*, não como dependência de runtime. Nenhuma dependência nova de runtime é necessária (Groq via `httpx` já existe).
- Entregável de conhecimento: nova skill de projeto `.cursor/skills/assistfin-agent-v2/SKILL.md` (loop, registry, política de confirmação, como adicionar ferramenta, como rodar eval), atualizando `assistfin-ai-agent` e `ai-agent-design-patterns`, `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`.

## Arquivos críticos
| Arquivo | Mudança |
|---|---|
| `app/agent/toolkit.py` (novo) | Registry de ferramentas + schemas + handlers |
| `app/agent/brain.py` (novo) | Loop agêntico, plano pendente, anti-alucinação |
| `app/agent/prompt_v2.py` (novo) | System prompt dinâmico |
| `app/agent/groq.py` | `chat_with_tools()`, retry, Whisper |
| `app/agent/confirm.py` (novo) | Execução em lote transacional |
| `app/services/finance.py` | Só funções de leitura novas (busca, projeção, comparação) |
| `app/agent/runner.py`, `app/routers/pages.py` | Desvio por flag para v2 + fallback legado |
| `app/routers/telegram.py`, `app/routers/whatsapp.py` (novos), `app/main.py` | Webhooks |
| `alembic/versions/022_agent_sessions.py`, `app/models.py` | `agent_sessions`, `user_channel_links` |
| `app/config.py`, `/opt/hosting/docker-compose.yml`, `.env` | Flags e tokens (segredos só no `.env`) |

## Guardrails mantidos
- LLM nunca calcula saldo/valor; só `finance.py`. Toda escrita confirmada. Toda query por `user_id`. Ids de escrita sempre validados como pertencentes ao usuário. Transferência nunca soma em receita/despesa.

## Verificação
1. `docker compose exec app2 pytest -q` — suíte atual inteira continua verde (legado intacto).
2. Novos testes com **LLM falso roteirizado** (sequência de tool calls): `tests/test_agent_v2_loop.py` (leitura→escrita→plano), `test_agent_v2_confirm.py` (lote atômico, rollback em erro), `test_agent_v2_isolation.py` (id de outro usuário rejeitado), `test_agent_v2_money_guard.py`, `test_telegram_webhook.py` (segredo, vínculo, callback).
3. `python -m app.scripts.agent_eval` contra Groq real: v2 ≥ legado e ≥ 90% de acerto nos casos.
4. Manual no web com `ENABLE_AGENT_V2` só para seu usuário: "gastei 35 no ifood e 120 no mercado ontem no cartão Nubank" → 2 ações num cartão de confirmação; "muda o mercado de ontem para 110" → busca + update; "apaga o ifood" → busca + delete confirmado; "como estou esse mês comparado ao anterior?" → análise com números das ferramentas.
5. Telegram: vincular, mandar texto e áudio, confirmar pelo botão, conferir no `/transactions`.
6. Rebuild: `cd /opt/hosting && docker compose build app2 && docker compose up -d app2`; `curl -s https://assistfin.com.br/health`.
