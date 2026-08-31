---
name: assistfin-ai-agent
description: >-
  Arquitetura do agente de IA do AssistFin: runner, wizards, intents, Groq,
  Ollama, ferramentas, chips e chat HTMX. Use ao alterar assistente, chat, LLM,
  prompt, confirmação, transferências, wizards ou quando o agente não entender
  intenção do usuário.
paths: app/agent/**, app/services/account_wizard.py, app/services/category_wizard.py, app/services/transaction_wizard.py, app/services/transaction_slots.py, app/services/recurrence.py, app/services/transfer_slots.py, app/services/multi_movements.py, app/services/multi_movement_flow.py, app/services/intents.py, app/services/tools.py, app/services/agent_suggestions.py, app/services/agent_state.py, app/templates/partials/agent_*.html, app/routers/pages.py
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
  → wizard transferência?
  → wizard transação? (datas antes de multi-lançamento)
  → try_begin_from_message (vários valores na mensagem)?
  → wizard conta / categoria?
  → exclusão pendente?
  → _resolve_intent (regras → Groq → Ollama)
  → create_account / create_category → wizard
  → WRITE_TOOLS → slots → confirmação → execute_tool
```

## Camadas de roteamento

| Camada | Quando |
|--------|--------|
| Regras (`try_rule_based_parse`) | "gastei 45", "transferir 100 da X para Y", "resumo" |
| `intents.py` | Listar vs cadastrar conta/categoria; detectar transferência |
| Wizards | Coleta guiada (conta, categoria, transação, transferência) |
| Groq | Intenção ambígua (`call_intent_llm`) |
| Ollama | Fallback local |

## WRITE_TOOLS (confirmação obrigatória)

`register_expense`, `register_income`, `register_transfer`, `realize_planned`, `update_transaction`, `update_account`, `delete_transaction`, `create_account`, `create_category`

## Chips de resposta

`agent_suggestions.py` + partial `agent_suggestions.html` — botões clicáveis quando o assistente pergunta conta, categoria, tipo, status, datas, etc.

## Cancelar

`agent_state.clear_agent_flow_state()` — limpa wizards, multi-movimento, exclusão pendente. Botão Cancelar no chat chama servidor (não só DOM).

## Wizards

| Wizard | Arquivo | Campos |
|--------|---------|--------|
| Transação | `transaction_wizard.py` + `transaction_slots.py` | tipo, status, datas, recorrência (fixo/frequência/término), valor, descrição, conta, categoria |
| Transferência | `transfer_slots.py` | valor, origem, destino |
| Conta | `account_wizard.py` | apelido, tipo, instituição, saldo |
| Categoria | `category_wizard.py` | nome, tipo |

### Slots de data (transação)

Após `status`, o wizard pergunta datas **antes** de valor/descrição:

| Status | Slots | Comportamento |
|--------|-------|---------------|
| `planned` | `competence_date`, `due_date` | Duas perguntas; `payment_date` fica vazio |
| `actual` | `payment_date` | Uma pergunta; replica em competência e vencimento |

- Parsing: `parse_slot_date()` → `parse_user_date()` (`hoje`, `ontem`, `amanhã`, `DD/MM/AAAA`, `agosto`, etc.)
- `is_date_only_message()` evita que datas isoladas (`10/08/2026`) sejam interpretadas como múltiplos valores em `parse_multi_movements`
- Com wizard ativo em slot de data, `try_begin_from_message` **não** inicia fluxo multi
- LLM **não** envia `status` nem inventa datas — só extrai se o usuário citou na mensagem
- Inferência de "ontem"/"hoje" na mensagem original pula a pergunta de data (realizado)

### Slots de recorrência

Após as datas, antes de valor:

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

## Chat UI (HTMX)

- `partials/agent_widget.html` → `POST /agent/chat`
- Confirmação: `partials/agent_response.html` com `confirmed=true`
- Chips em `agent_assistant_message.html`

## Checklist ao mudar o agente

- [ ] `ToolCall` em `schemas.py` + `tool_parse.py` KNOWN_TOOLS
- [ ] `execute_tool` + `format_tool_result` + `format_pending_confirmation`
- [ ] `SYSTEM_PROMPT` + heurística em `intents.py` / `tools.py`
- [ ] Chips em `agent_suggestions.py` se novo slot
- [ ] Testes: intents, wizards, runner escape

## Referência de ferramentas

[tools-reference.md](tools-reference.md)
