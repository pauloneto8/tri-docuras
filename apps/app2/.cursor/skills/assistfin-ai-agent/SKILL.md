---
name: assistfin-ai-agent
description: >-
  Arquitetura do agente de IA do AssistFin: runner, wizards, intents, Groq,
  Ollama, ferramentas, chips e chat HTMX. Use ao alterar assistente, chat, LLM,
  prompt, confirmação, transferências, wizards ou quando o agente não entender
  intenção do usuário.
paths: app/agent/**, app/chat_format.py, app/services/account_wizard.py, app/services/category_wizard.py, app/services/card_wizard.py, app/services/transaction_wizard.py, app/services/transaction_slots.py, app/services/realize_planned_slots.py, app/services/pay_invoice_slots.py, app/services/recurrence.py, app/services/transfer_slots.py, app/services/multi_movements.py, app/services/multi_movement_flow.py, app/services/intents.py, app/services/tools.py, app/services/agent_suggestions.py, app/services/agent_state.py, app/templates/partials/agent_*.html, app/routers/pages.py
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
  → _resolve_intent:
       atalhos (realize_planned, pay_invoice, register_expense, register_income)
       → Groq → Ollama
       → try_rule_based_parse (fallback)
  → create_account / create_category / create_card → wizard
  → WRITE_TOOLS → slots → confirmação → execute_tool
```

## Camadas de roteamento

| Camada | Quando |
|--------|--------|
| Wizards | Coleta guiada em andamento (conta, categoria, transação, transferência, cartão, fatura) |
| Atalhos em `_resolve_intent` | `realize_planned`, `pay_invoice`, `register_expense`, `register_income` |
| Groq | Intenção ambígua (`call_intent_llm`) — **primeiro** para o restante |
| Ollama | Fallback local |
| `try_rule_based_parse` | Fallback se o LLM falhar ("gastei 45", "transferir 100 da X para Y") |

## WRITE_TOOLS (confirmação obrigatória)

`register_expense`, `register_income`, `register_transfer`, `realize_planned`, `update_transfer`, `update_transaction`, `update_account`, `update_card`, `delete_card`, `delete_transaction`, `create_account`, `create_card`, `create_category`, `pay_invoice`

## Chips de resposta

`agent_suggestions.py` + partial `agent_suggestions.html` — botões clicáveis quando o assistente pergunta conta, categoria, tipo, status, datas, etc.

## Cancelar

`agent_state.clear_agent_flow_state()` — limpa wizards, multi-movimento, exclusão pendente. Botão Cancelar no chat chama servidor (não só DOM).

## Wizards

| Wizard | Arquivo | Campos |
|--------|---------|--------|
| Transação | `transaction_wizard.py` + `transaction_slots.py` | tipo, status, modo, parcelas (N, intervalo, índice, basis), datas, valor, descrição, conta, categoria |
| Realizar previsto | `realize_planned_slots.py` | previsto, pagamento, mesma conta?, conta |
| Transferência | `transfer_slots.py` | valor, origem, destino |
| Conta | `account_wizard.py` | apelido, tipo, instituição, saldo, data do saldo inicial |
| Cartão | `card_wizard.py` | apelido, instituição, fechamento, vencimento, limite, liquidação |
| Categoria | `category_wizard.py` | nome, tipo |
| Pagar fatura | `pay_invoice_slots.py` | fatura, conta de débito, data |

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
