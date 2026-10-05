# Plano: Colocar o agente v2 do AssistFin em operação — briefing para execução

**Status:** Fases A, B e H.1 concluídas; G concluída em 2026-10-05 (cron 06:00/06:05 + logrotate + `INSIGHTS_EMAILS`); C **parcial** — o free tier do Groq não cabe com os 83 casos (12.218 tokens por caso contra 200.000/dia por modelo), medidos 2 casos em [docs/eval/agent-eval-2026-10-05.md](../../docs/eval/agent-eval-2026-10-05.md), semveredito do critério. D, E e F dependem do usuário. Criado em 2026-10-04.
**Workspace:** `/opt/hosting/apps/app2` (FastAPI + Postgres, container `hosting-app2`). Repositório git em `/opt/hosting` (branch `main`, remoto `origin`). Responder ao usuário em **português**.
**Pré-requisito:** o código do plano [agente-autonomo-v2.md](agente-autonomo-v2.md) já está implementado e na `main` (commit `3722ac6`). **Não reimplemente nada daquele plano**; este plano cobre só deploy, configuração, validação e ajustes.

## Antes de começar (notas para o agente executor)

- Ler: `AGENTS.md`, `.cursor/skills/assistfin-agent-v2/SKILL.md`, `.cursor/skills/assistfin-implementation/SKILL.md`, `docs/OPERATIONS.md` (seções "Agente autônomo v2", "Telegram", "WhatsApp", "Resumo proativo diário") e `.cursor/plans/agente-autonomo-v2.md`.
- **Segredos só em `/opt/hosting/.env`.** Nunca imprimir valores do `.env` no terminal, em logs ou no chat (use `grep -c`/`awk` para checar se uma variável está preenchida, como em `awk -F= '/^APP2_TELEGRAM/{print $1, (length($2)>0?"ok":"VAZIO")}' .env`). Antes de editar o `.env`, faça uma cópia `.env.bak.<timestamp>` (padrão já usado no diretório).
- **Os testes usam o Postgres de produção** (criam usuários `*@example.com`). Rode-os num container descartável com o código montado, sem rebuild:
  ```bash
  cd /opt/hosting
  docker compose run --rm --no-deps -T -v "$PWD/apps/app2:/app" --entrypoint python app2 -m pytest -q -p no:cacheprovider
  ```
  **Linha de base (2026-10-04):** 446 passaram, 0 falharam (~85 s).
- **Deploy:** `cd /opt/hosting && docker compose build app2 && docker compose up -d app2`, depois `curl -s https://assistfin.com.br/health`. Antes de qualquer deploy, backup do banco (`app/services/db_backup.py`/painel `/admin`, ou `pg_dump` no container `hosting-app2-db` para `apps/app2/data/backups/`).
- **Commits:** um por fase, mensagens no padrão do repo (`feat(app2): …`, `fix(app2): …`, `chore(app2): …`, `docs(app2): …`), terminando com a linha `Co-Authored-By` da sessão. Commit e push **só com autorização do usuário**. Não incluir as mudanças pendentes do app1 (`apps/app1/frontend/...`), que não são deste plano.
- **Passos marcados com 👤 dependem do usuário** (contas externas, celular, decisões). Pare, explique exatamente o que ele precisa fazer e espere; não invente valores nem pule a validação.

## Situação verificada em 2026-10-04

| Item | Estado |
|---|---|
| Código v2, migrações `022`/`023` | Na `main`; migrações aplicadas (`alembic current` = `023`) |
| Container `hosting-app2` | **Desatualizado**: imagem de 2026-10-04 00:54 (-03). Diferem do repo: `app/agent/brain.py`, `app/agent/groq.py`, `app/agent/prompt_v2.py`, `app/scripts/agent_eval.py` |
| Retry/backoff do Groq (`RETRY_STATUS`, `_retry_delay`, `_post_json` em `groq.py`) | Só no repo; **não está em produção** |
| Erros 429 do Groq | 12 tracebacks no log (o último às 2026-10-04 09:15Z), via `runner.py::_process_message_v2` → `brain.run` → `groq.chat_with_tools`; a requisição respondeu 200 (houve fallback) |
| Flags | `ENABLE_AGENT_V2=true`, `AGENT_V2_USERS=1`; `ENABLE_AI_INSIGHTS=false` |
| Telegram / WhatsApp | Todas as variáveis `APP2_TELEGRAM_*` e `APP2_WHATSAPP_*` **vazias**; `user_channel_links` com 0 linhas |
| Cron | Nenhum crontab no host (nem `notify_channels`, nem `generate_insights`) |
| `.env.example` | Sem as variáveis novas do v2 |
| Eval contra Groq real | Sem registro de execução |
| Aviso nos testes | `datetime.utcnow()` deprecado em `app/services/channels.py:162` |

## Fases

### Fase A — Sincronizar produção com a `main`
1. Confirmar a divergência: para cada arquivo de `git ls-files app alembic`, comparar `md5sum` do disco com `docker exec hosting-app2 sh -c "md5sum < /app/<arquivo>"`. Esperado: só os 4 arquivos da tabela acima.
2. Rodar a suíte completa (comando acima); exigir 446/446 verde.
3. Backup do banco (ver acima) e conferir que o arquivo foi gerado e não está vazio.
4. Deploy (build + up). Conferir `/health`, `docker logs --since 5m hosting-app2` sem traceback e repetir o passo 1: **nenhum arquivo diferente**.
5. Adicionar ao `/opt/hosting/.env.example`, sem valores reais, as variáveis já usadas pelo compose: `APP2_ENABLE_AGENT_V2=false`, `APP2_AGENT_V2_USERS=`, `APP2_TELEGRAM_BOT_TOKEN=`, `APP2_TELEGRAM_WEBHOOK_SECRET=`, `APP2_WHATSAPP_ACCESS_TOKEN=`, `APP2_WHATSAPP_PHONE_NUMBER_ID=`, `APP2_WHATSAPP_VERIFY_TOKEN=`, `APP2_WHATSAPP_APP_SECRET=`, com um comentário curto por bloco.
- **Pronto quando:** container idêntico ao repo, `/health` OK, `.env.example` atualizado. Commit: `chore(app2): documenta variaveis do agente v2 no .env.example`.

### Fase B — Rate limit (429) do Groq
1. Após a Fase A, acompanhar o log por novos 429 (`docker logs -t hosting-app2 2>&1 | grep -c '429'` antes/depois de uso real ou do eval da Fase C).
2. Ler `groq.py::_post_json`/`_retry_delay` e `runner.py::_process_message_v2` e confirmar por teste o comportamento esperado:
   - 429 com `Retry-After` → espera e tenta de novo (respeitando o teto de ~30 s do loop do `brain.py`);
   - 429 persistente → `_process_message_v2` cai no pipeline legado **sem traceback de nível ERROR** (registrar `logger.warning` com status e tentativa) e o usuário recebe resposta normal, nunca erro 500.
   Se `tests/` ainda não cobrir isso, criar `tests/test_groq_retry.py` com `httpx.MockTransport` (sem rede): 429→200 tem sucesso; 429×N cai no legado; `Retry-After` é respeitado (com `asyncio.sleep` mockado).
3. Se os 429 continuarem frequentes após o retry, investigar a causa antes de mexer em limites: contar chamadas ao Groq por mensagem (métricas de `conversation_messages` com `source="agent-v2"`: iterações e tokens). Opções em ordem de preferência: reduzir iterações redundantes (dedup/prompt), baixar `reasoning_effort` nas mensagens simples, espaçar chamadas paralelas. **Não trocar de modelo nem de provedor sem perguntar ao usuário 👤.**
- **Pronto quando:** testes de retry verdes; nenhum traceback 429 no log após 24 h de uso. Commit: `fix(app2): ...` ou `test(app2): ...`, conforme o que mudar.

### Fase C — Avaliação contra o Groq real (critério do plano v2)
1. `docker compose exec -T app2 python -m app.scripts.agent_eval --dry-run` (valida o YAML).
2. `docker compose exec -T app2 python -m app.scripts.agent_eval --user-id 1 --mode both --delay 3`. Se der 429, aumente `--delay` e use `--limit` em lotes. O script não grava no banco (v2 só gera plano pendente; o legado só resolve a intenção).
3. Salvar o relatório em `docs/eval/agent-eval-2026-10-XX.md`: acerto de ferramenta e de argumentos, legado × v2, e a lista de casos que falharam com o motivo.
4. **Critério:** v2 ≥ legado **e** v2 ≥ 90%. Se não atingir, iterar em `app/agent/prompt_v2.py` e nas `description` das ferramentas em `app/agent/toolkit.py` (nunca mover cálculo para o LLM), rodar de novo e registrar antes/depois. Não “ajustar” o `cases.yaml` para fazer passar; só corrigir caso comprovadamente errado, explicando no relatório.
- **Pronto quando:** relatório salvo com o critério atendido (ou, se não atendido após 3 iterações, relatório com o diagnóstico e pergunta ao usuário 👤). Commit: `docs(app2): resultado do eval do agente v2` (+ `fix(app2): ...` se ajustou prompt/toolkit).

### Fase D — Validação manual no chat web 👤
O agente não tem a sessão do usuário; o **usuário** executa e o agente confere no banco e nos logs.
1. Pedir ao usuário que mande no chat web, nesta ordem:
   - "gastei 35 no ifood e 120 no mercado ontem no cartão Nubank" → esperado: **um** cartão de confirmação com 2 ações; confirmar.
   - "muda o mercado de ontem para 110" → busca + update, confirmação.
   - "apaga o ifood" → busca + delete confirmado.
   - "como estou esse mês comparado ao anterior?" → análise com números vindos das ferramentas.
2. Depois de cada passo, conferir em `transactions`/`conversation_messages` (filtrando por `user_id = 1`) que as escritas batem com o que foi confirmado e que nenhum valor em R$ da resposta deixou de vir de uma ferramenta.
3. Se o usuário não quiser que esses lançamentos fiquem no histórico, usar valores/descrições de teste e apagá-los no fim, **pelo próprio chat** (para exercitar o delete).
- **Pronto quando:** os 4 cenários se comportam como esperado; anotar o resultado no relatório da Fase C.

### Fase E — Telegram
1. 👤 O usuário cria o bot no @BotFather e coloca o token no `.env` (`APP2_TELEGRAM_BOT_TOKEN=`). Se ele preferir colar o token no chat, o agente grava no `.env` sem ecoá-lo.
2. Agente gera o segredo do webhook (`openssl rand -hex 32`) e grava em `APP2_TELEGRAM_WEBHOOK_SECRET` (backup do `.env` antes).
3. `docker compose up -d app2`; confirmar que o container recebeu as variáveis (checar só se estão preenchidas).
4. `docker compose exec -T app2 python -m app.scripts.set_telegram_webhook`, depois `... --info`: URL `https://assistfin.com.br/telegram/webhook/...`, sem `last_error_message`.
5. Conferir no nginx (`/opt/hosting/nginx`) que `/telegram/webhook` chega ao app2 e tem rate limit; um POST sem o header `X-Telegram-Bot-Api-Secret-Token` deve dar 401/403.
6. 👤 O usuário abre `/channels`, gera o código e manda `/vincular <código>` ao bot. O agente confere uma linha nova em `user_channel_links`.
7. 👤 Teste ponta a ponta: texto ("gastei 42 no posto ontem no Nubank"), **áudio** com a mesma frase (Whisper) e confirmação pelo botão inline. O agente confere a transação em `transactions` e o `source`/canal em `conversation_messages`.
- **Pronto quando:** vínculo, texto, áudio e botão funcionam. Commit só se houver ajuste de código/docs.

### Fase F — WhatsApp (Meta Cloud API) 👤 — bloqueada até a Meta
1. Perguntar ao usuário se já tem app e número verificados na Meta. **Se não, registrar a fase como bloqueada e seguir para a G.**
2. Com as credenciais: gravar `APP2_WHATSAPP_ACCESS_TOKEN`, `APP2_WHATSAPP_PHONE_NUMBER_ID`, `APP2_WHATSAPP_APP_SECRET` e um `APP2_WHATSAPP_VERIFY_TOKEN` gerado (`openssl rand -hex 24`); `up -d app2`.
3. 👤 O usuário configura na Meta a URL `https://assistfin.com.br/whatsapp/webhook` com o verify token e assina o campo `messages`. O agente confere o `hub.challenge` no log.
4. Mesmos testes da Fase E (vínculo, texto, áudio, botão de confirmar). Um POST com assinatura `X-Hub-Signature-256` inválida deve ser rejeitado.

### Fase G — Proatividade (cron)
1. 👤 Perguntar: ligar `APP2_ENABLE_AI_INSIGHTS=true`? (os insights agora usam Groq e não Claude; valores continuam validados em Python). Horário dos envios (sugestão 06:00, `America/Recife`; o host usa -03).
2. Rodar uma vez à mão e ler a saída:
   `docker compose exec -T app2 python -m app.scripts.generate_insights` e `docker compose exec -T app2 python -m app.scripts.notify_channels` (no-op seguro sem vínculos; com o Telegram vinculado, o usuário deve receber o resumo 👤).
3. Instalar no crontab do root (os comandos de `docs/OPERATIONS.md`, com `cd /opt/hosting`):
   ```
   0 6 * * * cd /opt/hosting && docker compose exec -T app2 python -m app.scripts.generate_insights >> /var/log/assistfin-insights.log 2>&1
   5 6 * * * cd /opt/hosting && docker compose exec -T app2 python -m app.scripts.notify_channels >> /var/log/assistfin-notify.log 2>&1
   ```
   Confirmar que o `docker` está no `PATH` do cron (senão, usar o caminho absoluto de `command -v docker`) e criar `/etc/logrotate.d/assistfin` (semanal, 4 rotações, `compress`, `missingok`).
4. No dia seguinte, conferir os dois logs.
- **Pronto quando:** cron instalado e uma execução real registrada sem erro.

### Fase H — Acabamento e documentação
1. Trocar `datetime.utcnow()` por `datetime.now(timezone.utc)` em `app/services/channels.py:162` (e outros usos no código do v2, `grep -rn utcnow app/`), mantendo a coluna compatível (se for `timestamp without time zone`, gravar `.replace(tzinfo=None)`). Suíte verde, sem o `DeprecationWarning`.
2. 👤 Perguntar se `AGENT_V2_USERS` deve incluir outros usuários ou se o v2 vira padrão para todos (esvaziar a lista vale para todos? Confirmar em `app/config.py` antes de afirmar).
3. Atualizar o **Status** de `agente-autonomo-v2.md` e deste plano, a seção "Planos" do `AGENTS.md`, `docs/OPERATIONS.md` (horários do cron e logs reais) e `docs/CHANGELOG.md`.
4. Deploy final (backup → build → up → `/health`), commit e, com autorização, push.

## Ordem e dependências
`A → B → C → D` em sequência (C depende do retry em produção; D depende de C estar aceitável). `E` pode começar logo após `A`, assim que o usuário tiver o token. `F` depende da Meta e não bloqueia nada. `G` depende de `E` (precisa de canal vinculado para o `notify_channels` ter efeito). `H` por último.

## Guardrails (não negociáveis)
- LLM nunca calcula saldo/valor; só `finance.py`/`agent_reads.py`. Toda escrita passa por confirmação. Toda query filtra por `user_id`. Transferência não entra em receita/despesa.
- Não desligar o fallback legado, não alterar migrações já aplicadas (`022`/`023`), não apagar dados de usuários reais.
- Em caso de regressão após um deploy: `APP2_ENABLE_AGENT_V2=false` no `.env` + `docker compose up -d app2` é o rollback imediato; depois investigar.

## Verificação final (checklist)
- [ ] Container idêntico à `main`; `/health` OK
- [ ] Sem traceback de 429 no log por 24 h; testes de retry verdes
- [ ] Relatório do eval salvo: v2 ≥ legado e ≥ 90%
- [ ] 4 cenários manuais do web OK
- [ ] Telegram: vínculo, texto, áudio, botão OK
- [ ] WhatsApp: OK **ou** registrado como bloqueado pela Meta
- [ ] Cron de insights e de notificações instalado, com uma execução registrada
- [ ] Suíte completa verde, sem warnings do código do app; docs e status dos planos atualizados
