---
name: assistfin-ai-agent
description: >-
  Arquitetura do agente de IA do AssistFin: runner, wizards, intents, Groq,
  ferramentas, chips e chat HTMX. Use ao alterar assistente, chat, LLM,
  prompt, confirmação, transferências, wizards ou quando o agente não entender
  intenção do usuário.
paths: app/agent/**, app/chat_format.py, app/services/account_wizard.py, app/services/category_wizard.py, app/services/card_wizard.py, app/services/transaction_wizard.py, app/services/transaction_slots.py, app/services/realize_planned_slots.py, app/services/pay_invoice_slots.py, app/services/recurrence.py, app/services/transfer_slots.py, app/services/multi_movements.py, app/services/multi_movement_flow.py, app/services/intents.py, app/services/tools.py, app/services/agent_suggestions.py, app/services/agent_state.py, app/services/agent_preferences.py, app/services/insights.py, app/scripts/generate_insights.py, app/templates/partials/agent_*.html, app/routers/pages.py
---

# AssistFin — Agente de IA

## Arquitetura (híbrida stateful)

- **LLM stateless** escolhe ferramenta (JSON `ToolCall`).
- **Runtime stateful**: sessão Starlette, wizards, `conversation_messages`.
- **Execução determinística**: `execute_tool()` — modelo nunca calcula saldos.

## Fluxo de `process_message` (`app/agent/runner.py`)

```
mensagem
  → multi-movimento em andamento (pending_movements)?
  → wizard pagar fatura?
  → wizard transferência?
  → wizard realizar previsto?
  → wizard transação? (datas/modo/parcelas/recorrência antes de multi-lançamento)
  → try_begin_from_message (vários valores na mensagem)?
  → wizard cartão? (cadastro em andamento)
  → wizard conta / categoria?
  → exclusão pendente?
  → escopo de parcelas pendente (editar parcela com seguintes)?
  → _resolve_intent:
       atalhos (realize_planned, pay_invoice, list_categories, create_category,
                register_expense, register_income)
       → Groq
       → try_rule_based_parse (fallback)
  → create_account / create_category / create_card → wizard
  → WRITE_TOOLS → slots → (update_transaction: perguntar installment_scope se preciso)
       → confirmação → execute_tool
```

## Camadas de roteamento

| Camada | Quando |
|--------|--------|
| Wizards | Coleta guiada em andamento (conta, categoria, transação, transferência, cartão, fatura) |
| Atalhos em `_resolve_intent` | `realize_planned`, `pay_invoice`, `register_expense`, `register_income` |
| Groq | Intenção ambígua (`call_intent_llm`) — extrai todos os campos presentes na mensagem |
| `try_rule_based_parse` | Fallback se o Groq falhar ("gastei 45", "transferir 100 da X para Y") |

Wizard de lançamento: **só pergunta slots vazios** após inferência (`_apply_inference` / `_wizard_from_tool_call`). Ex.: “lançado no cartão do Mercado Pago” → `card_name` sem reperguntar conta de liquidação; confirmação exibe **Cartão:**. Com cartão e conta cadastrados e mensagem ambígua, pergunta `payment_source` antes de status.

## WRITE_TOOLS (confirmação obrigatória)

`register_expense`, `register_income`, `register_transfer`, `realize_planned`, `update_transfer`, `update_transaction`, `update_account`, `update_card`, `delete_card`, `delete_transaction`, `create_account`, `create_card`, `create_category`, `update_category`, `delete_category`, `pay_invoice`

## Chips de resposta

`agent_suggestions.py` + partial `agent_suggestions.html` — botões clicáveis quando o assistente pergunta conta, categoria, tipo, status, datas, etc.

## Cancelar

`agent_state.clear_agent_flow_state()` — limpa wizards, multi-movimento, exclusão pendente. Botão Cancelar no chat chama servidor (não só DOM).

## Wizards

| Wizard | Arquivo | Campos |
|--------|---------|--------|
| Transação | `transaction_wizard.py` + `transaction_slots.py` | tipo, **payment_source** (cartão/conta), status, modo, parcelas (N, intervalo, índice, basis), datas, valor, descrição, **card_name** ou **account_name**, categoria |
| Realizar previsto | `realize_planned_slots.py` | previsto, pagamento, mesma conta?, conta |
| Transferência | `transfer_slots.py` | valor, origem, destino |
| Conta | `account_wizard.py` | apelido, tipo, instituição, saldo, data do saldo inicial |
| Cartão | `card_wizard.py` | apelido, instituição, fechamento, vencimento, limite, liquidação |
| Categoria | `category_wizard.py` | nome(s), tipo; lote com vírgulas; “Vale e Auxílio” = um nome |
| Pagar fatura | `pay_invoice_slots.py` | fatura, conta de débito, data |
| Escopo de parcela | `installment_scope_flow.py` | ao editar parcela com seguintes: só esta / esta e as seguintes |

### Slots de data (transação)

Ordem depende de **status** e **modo**:

| Contexto | Slots | Comportamento |
|----------|-------|---------------|
| `planned`, não parcelado | `competence_date`, `due_date` | Duas perguntas; `payment_date` vazio |
| `actual`, não parcelado | `payment_mode` primeiro, depois `payment_date` | Pagamento replica em competência e vencimento |
| **parcelado** | Após N, intervalo e `installment_start_index` | Competência e vencimento **da parcela**; depois `payment_date` se realizado |
| **parcelado** + inferência | — | `ontem`/`hoje` na mensagem **não** preenchem slots; escolher *parcelado* limpa datas genéricas |

- Parsing: `parse_slot_date()` → `parse_user_date()` (`hoje`, `ontem`, `amanhã`, `DD/MM/AAAA`, `agosto`, etc.)
- Parcelado: `payment_date` **não** altera competência/vencimento já informados
- `is_date_only_message()` evita que datas isoladas sejam interpretadas como múltiplos valores
- LLM **não** envia `status`, `installment_amount_basis`, `installment_start_index` nem inventa datas de parcelamento

### Forma de pagamento (cartão vs conta)

Quando o usuário tem cartões cadastrados e a mensagem não deixa claro:

| Slot | Pergunta | Inferência |
|------|----------|------------|
| `payment_source` | Cartão ou conta? | “no cartão”, “lançado no cartão do X” → `card` sem perguntar |
| `card_name` | Qual cartão? | `infer_card_name()` + chips dos cartões ativos |
| `account_name` | Qual conta? | `infer_account_name()` — não usado quando `payment_source=card` |

Confirmação (`format_pending_confirmation`): exibe **Cartão:** ou **Conta:** conforme `card_name`.

### Slots de parcelamento

Após `payment_mode=installment`:

| Slot | Pergunta |
|------|----------|
| `installment_count` | Em quantas vezes? |
| `installment_interval` | Mensal, semanal ou quinzenal |
| `installment_start_index` | Primeira parcela ou qual está lançando (1…N) |
| `competence_date` | Competência da parcela X/N |
| `due_date` | Vencimento da parcela X/N (ancora cronograma) |
| `payment_date` | Só se realizado — caixa, independente do vencimento |
| `installment_amount_basis` | Valor total da compra ou valor de cada parcela |

`INSTALLMENT_SLOTS` entram nas guardas anti-multi em `multi_movement_flow.py`.

### Slots de recorrência

Após datas (lançamento **não** parcelado), antes de valor:

| Slot | Pergunta | Respostas |
|------|----------|-----------|
| `is_recurring` | É fixo/repete? | sim/não — **não** aqui não cancela o wizard |
| `frequency` | Frequência | diária, semanal, mensal |
| `recurrence_end_date` | Tem término? | não ou data |

- `RECURRENCE_SLOTS` entram nas guardas anti-multi em `multi_movement_flow.py`
- LLM pode inferir `frequency` de frases como "aluguel todo mês"

Escape: intenção diferente → `clear_wizard` + `None` (delega ao runner).

## Prompt

- `SYSTEM_PROMPT` em `app/agent/prompt.py`
- JSON único `{"tool","arguments"}`
- Diferenciar: `list_accounts` vs `list_transactions` vs `register_transfer`
- Diferenciar: `update_account` (conta bancária) vs `update_card` (cartão) vs `update_transaction` (despesa/receita) vs `update_transfer` (par de transferência)
- Diferenciar: `delete_card` (cartão) vs `delete_transaction` (lançamento)

## Resumo após lançamento

`finance.enrich_register_result()` anexa `context_summary` ao resultado de `register_expense` / `register_income` / `realize_planned` (e multi-movimento). `format_tool_result` concatena ao texto: fatura do cartão (`invoice_context_summary`) ou saldo da conta (`account_context_summary`).

## Inteligência proativa (Claude, opcional)

Segundo modelo, **só leitura/explicação** — nunca tool-calling nem escrita.
`app/agent/claude.py` (mesmo padrão httpx de `groq.py`) + `app/services/insights.py`
(`generate_monthly_insight`): monta prompt só com números já calculados por
`get_summary`/`get_budget_status`, chama Claude Haiku, valida que todo valor
monetário no texto gerado bate com um dos valores enviados (descarta se não
bater) e salva em `agent_insights`. Exibido nas boas-vindas do chat
(`agent_welcome` em `pages.py`) quando há insight do mês corrente. Desligado
por padrão (`ENABLE_AI_INSIGHTS`/`ANTHROPIC_API_KEY`).

Fase 3 (fallback de NLU) também implementada: `_resolve_intent` (`runner.py`)
tenta Claude Haiku (`call_claude_tool_call`) com o mesmo `SYSTEM_PROMPT` de
tool-calling só depois que Groq **e** `try_rule_based_parse` falharem — nunca
substitui o caminho comum. Desligado por padrão (`ENABLE_AI_NLU_FALLBACK`).

Fase 4 (memória de personalização) implementada — **sem LLM**, sempre ativa:
`app/services/agent_preferences.py`. Depois de um `register_expense`/
`register_income` confirmado (lançamento único, não recorrente, não
parcelado), se a mesma descrição normalizada já se repetiu **exatamente 3
vezes seguidas** com a mesma categoria e/ou forma de pagamento, o agente
pergunta ("quer que eu lembre?"); só grava em `agent_description_preferences`
(migração `021`) com "sim" explícito. Leitura pré-preenche categoria/cartão/
conta em `transaction_slots.py` (`infer_category_name`,
`_infer_and_apply_payment_source`) — mesmo princípio das outras inferências
(`card_name`), confirmação de escrita continua obrigatória. Oferta duplicada
em `runner.py` e `pages.py` (`offer_description_preference_from_result`);
resposta sim/não tratada no topo de `process_message`
(`try_process_pending_description_preference`); `agent_state.py` evita que
"não" vire cancelamento global enquanto essa pergunta está pendente.

Fase 5 (orquestrador multi-etapas) implementada — `app/agent/orchestrator.py`.
Única parte do agente que usa o SDK oficial `anthropic` (Tool Runner,
`client.beta.messages.tool_runner`) em vez de httpx puro — o resto (Fases 1-3)
continua em `app/agent/claude.py`. `looks_like_broad_request()` detecta no
`runner.py`, **antes** do roteamento de intenção única, um pedido amplo
(verbo de revisão/análise + mensagem longa + sem valor monetário explícito) e
chama `run_orchestrator`: Claude Sonnet (`ANTHROPIC_MODEL_REASONING`) com
`effort: medium`, até 5 iterações, só as ferramentas de LEITURA já existentes
(`list_transactions`, `get_summary`, `get_budget_status`, `list_categories`,
`list_invoices`) — sem acesso a nenhuma ferramenta de escrita. Mesma validação
anti-alucinação da Fase 2 (todo `R$ x,xx` citado precisa ter vindo de uma
ferramenta chamada na execução; se não, descarta). Ação sugerida fica só no
texto — sem escrita direta; se o usuário topar, a mensagem seguinte dele volta
ao `process_message` normal, que já enxerga o histórico recente via
`build_intent_context` e passa pela confirmação de escrita de sempre.
Desligado por padrão (`ENABLE_AI_ORCHESTRATOR`/`ANTHROPIC_API_KEY`).

Plano completo: `.cursor/plans/agente-inteligencia-proativa.md`.

## Chat UI (HTMX)

- `partials/agent_widget.html` → `POST /agent/chat`
- Avatares: `agent_avatar.html` (assistente à esquerda, inicial do usuário à direita)
- Corpo: `agent_message_body.html` com filtro `chat_md` (`app/chat_format.py`) — HTML escapado, `*negrito*`, listas
- Chips **fora** do balão: `agent_suggestions.html`
- Confirmação **fora** do balão: `agent_confirm_actions.html` (`confirmed=true`)
- Welcome HTMX: `agent_assistant_message.html`

## Checklist ao mudar o agente

- [ ] `ToolCall` em `schemas.py` + `tool_parse.py` KNOWN_TOOLS
- [ ] `execute_tool` + `format_tool_result` + `format_pending_confirmation`
- [ ] `SYSTEM_PROMPT` + heurística em `intents.py` / `tools.py`
- [ ] Chips em `agent_suggestions.py` se novo slot
- [ ] Testes: intents, wizards, runner escape

## Referência de ferramentas

[tools-reference.md](tools-reference.md)
