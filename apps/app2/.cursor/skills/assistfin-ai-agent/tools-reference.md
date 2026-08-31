# Ferramentas e arquivos do agente

## Arquivos

| Arquivo | Responsabilidade |
|---------|------------------|
| `app/agent/runner.py` | Orquestração `process_message` |
| `app/agent/llm.py` | `call_llm`, `call_intent_llm` |
| `app/agent/groq.py` | API Groq (JSON mode) |
| `app/agent/ollama.py` | API Ollama local |
| `app/agent/prompt.py` | SYSTEM_PROMPT + `extract_json` |
| `app/agent/tool_parse.py` | KNOWN_TOOLS, unsupported_action |
| `app/services/intents.py` | listar/cadastrar conta/categoria, transferência |
| `app/services/tools.py` | Regras, execute, formatação, `parse_user_date`, `is_date_only_message` |
| `app/services/multi_movements.py` | Parser de vários lançamentos em uma mensagem |
| `app/services/multi_movement_flow.py` | Fluxo guiado de confirmação multi |
| `app/services/transaction_slots.py` | Slots de transação (status, datas, recorrência, conta, categoria) |
| `app/services/recurrence.py` | Regras fixas, horizonte de previstos, encerrar série |
| `app/services/transfer_slots.py` | Wizard de transferência |
| `app/services/agent_suggestions.py` | Chips clicáveis |
| `app/services/agent_state.py` | Limpar estado ao cancelar |
| `app/services/text_correction.py` | Ortografia descrições/categorias |
| `app/routers/pages.py` | `/agent/chat`, `/agent/welcome`, confirmação |

## Ferramentas (`ToolCall`)

| Ferramenta | Argumentos principais |
|------------|----------------------|
| `register_expense` | amount, description, account_name?, category_name?, competence_date?, due_date?, payment_date?, transaction_date?, frequency?, recurrence_end_date? — **sem** `status` (wizard pergunta) |
| `register_income` | idem |
| `register_transfer` | amount, from_account_name?, to_account_name?, description?, transaction_date? |
| `realize_planned` | planned_id?, description?, amount?, account_name?, category_name?, competence_date?, due_date?, payment_date?, transaction_date? |
| `update_transaction` | transaction_id?, amount?, description?, account_name?, category_name?, transaction_date?, competence_date?, due_date?, payment_date? |
| `delete_transaction` | transaction_id?, amount?, description? |
| `update_account` | account_id?, account_name?, opening_balance?, opening_balance_date?, … |
| `list_transactions` | limit?, type?, status? (`actual` \| `planned` \| `all`) |
| `list_accounts` | {} |
| `list_categories` | {} |
| `get_summary` | year?, month? |
| `get_budget_status` | year?, month? |
| `create_account` | name, account_type, … |
| `create_category` | name, type, keywords? |
| `categorize` | description, type? |
| `unsupported_action` | reason |

## Variáveis de ambiente

- `APP2_GROQ_API_KEY` — intenção ambígua
- `APP2_GROQ_MODEL` — default `openai/gpt-oss-120b`
- `OLLAMA_URL`, `OLLAMA_MODEL` — fallback (`qwen3:1.7b`)

## Testes recomendados

```bash
docker compose exec -T app2 python -m pytest \
  tests/test_intents.py \
  tests/test_transfers.py \
  tests/test_runner_wizard_escape.py \
  tests/test_transaction_wizard.py \
  tests/test_transaction_slots.py \
  tests/test_transaction_dates.py \
  tests/test_parse_date.py \
  tests/test_planned_transactions.py \
  tests/test_recurrence.py \
  tests/test_multi_movements.py \
  tests/test_account_wizard.py \
  tests/test_category_wizard.py \
  tests/test_list_accounts.py \
  tests/test_list_categories.py \
  tests/test_agent_suggestions.py \
  tests/test_agent_cancel.py \
  -q
```

## Debug de conversas

```sql
SELECT role, content, tool_used, source, created_at
FROM conversation_messages
ORDER BY created_at DESC LIMIT 20;
```
