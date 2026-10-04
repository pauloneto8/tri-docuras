---
name: assistfin-agent-v2
description: >-
  Motor de agente autônomo v2 do AssistFin: loop de ferramentas no Groq,
  registry (toolkit), confirmação em lote, canais (web/Telegram/WhatsApp),
  leituras novas e eval. Use ao mexer em app/agent/brain.py, toolkit.py,
  prompt_v2.py, confirm.py, groq.py, agent_reads.py, channels.py, webhooks,
  proatividade ou ao adicionar/alterar ferramenta do agente v2.
paths: app/agent/**, app/services/agent_reads.py, app/services/channels.py, app/services/proactive.py, app/routers/telegram.py, app/routers/whatsapp.py, app/scripts/agent_eval.py, app/scripts/notify_channels.py, app/scripts/set_telegram_webhook.py, tests/agent_eval/**, alembic/versions/022_agent_sessions.py, alembic/versions/023_channel_link_multi.py
---

# AssistFin — Agente autônomo v2

Motor de chat que substitui a cascata de wizards por um **loop de ferramentas**
(LLM escolhe entre 31 ferramentas, Python executa). Ativa por
`ENABLE_AGENT_V2` + `AGENT_V2_USERS`; o motor legado
(`assistfin-ai-agent`) fica como fallback/rollback.

## Fluxo (`app/agent/runner.py::process_message`)

```
_agent_v2_enabled(user_id)?
  ├─ sim → _process_message_v2
  │     ├─ plano pendente na sessão (agent_v2_plan)?
  │     │     sim → confirm_plan / cancel_plan / expira (TTL 30 min)
  │     └─ brain.run(db, user_id, message, channel, history?)
  │           → readings executam; writes viram pending_plan
  │     needs_confirmation → guarda plano + "responda sim/não"
  └─ não → fluxo legado
```

- `brain.run` recebe `llm=` injetável (testes usam LLM falso roteirizado).
- `BrainResult.response`, `.pending_plan`, `.tool_calls`, `.metrics`
  (iterations/latency/tool names).
- Falha no v2 → `None` → cai no legado (não derruba o chat).

## Adicionar uma ferramenta

1. Defina o `ToolSpec` em `app/agent/toolkit.py` (`name`, `description`,
   `parameters` JSON Schema, `handler`, `read`/`write`).
2. Handler de leitura: implemente em `app/services/agent_reads.py` (só Python,
   reusa `finance.py`/`credit_cards.py`). **Nunca** calcula saldo no LLM.
3. Handler de escrita: reaproveite `app/services/tools.py::execute_tool`; a
   escrita **não** roda no loop — vira `pending_plan` e só executa em
   `confirm_plan`.
4. Se for escrita, adicione o nome a `WRITE_TOOLS` em `app/agent/runner.py`.
5. Rode `pytest -q` e, se aplicável, `python -m app.scripts.agent_eval`.

## Política de confirmação (inegociável)

- Toda escrita exige confirmação: `pending_plan` = `{"actions": [...]}` com
  prévia via `format_pending_confirmation`.
- `confirm_plan()` executa o lote e reporta por ação; `cancel_plan()` descarta;
  `is_expired()` descarta após `PLAN_TTL_MINUTES = 30`.
- Toda query/validação por `user_id`; ids de escrita validados como do usuário.
- Transferência nunca soma receita/despesa; valores só em `finance.py`.

## Canais

- `app/services/channels.py`: `create_link_code`/`consume_link_code` (código de
  6 dígitos, 10 min), `handle_channel_message` (brain + histórico + persiste
  plano em `AgentSession`), `send_telegram_message`/`send_whatsapp_message`
  (botões), `transcribe_audio` (Groq Whisper `whisper-large-v3-turbo`).
- Webhooks públicos (`app/main.py::_is_public_path`): Telegram valida
  `X-Telegram-Bot-Api-Secret-Token`; WhatsApp valida `X-Hub-Signature-256`.
  Ambos sempre respondem 200.
- Proatividade: `app/services/proactive.py::build_daily_digest` (Python puro) +
  `python -m app.scripts.notify_channels` (cron).

## Eval

```
python -m app.scripts.agent_eval            # v2 vs legado, casos de tests/agent_eval/cases.yaml
python -m app.scripts.agent_eval --dry-run  # valida o YAML sem chamar a API
```

Casos só de leitura; matcher por tool + subconjunto de args, `expected_reads`
e `answer`. Threshold 90%.

## Comandos

```
# testes sem rebuild (monta o fonte)
cd /opt/hosting && docker compose run --rm --no-deps -T \
  -v "$PWD/apps/app2:/app" -e PYTHONDONTWRITEBYTECODE=1 \
  --entrypoint python app2 -m pytest -q -p no:cacheprovider

# migração
docker compose run --rm --no-deps -T -v "$PWD/apps/app2:/app" \
  --entrypoint alembic app2 upgrade head

# deploy
cd /opt/hosting && docker compose build app2 && docker compose up -d app2
```

## Alertas

- Não reabrir o vetor antigo de confirmação (JSON de ação no form). No v2 a
  confirmação é pela sessão (`agent_v2_plan`) / `AgentSession`, via "sim/não".
- `CardInvoice` não tem `is_paid`: use `status` + `paid_at`.
- Dinheiro em centavos no banco; `format_brl` só na saída.
