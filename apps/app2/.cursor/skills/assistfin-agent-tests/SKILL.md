---
name: assistfin-agent-tests
description: >-
  Testes do agente de IA do AssistFin: pytest, mocks de Groq/Ollama, wizards,
  intents, transferências e conversas. Use ao criar ou corrigir testes do chat,
  runner, LLM ou antes de deploy de mudanças no agente.
paths: tests/test_*wizard*.py, tests/test_intents.py, tests/test_intent_llm.py, tests/test_runner_wizard_escape.py, tests/test_llm_fallback.py, tests/test_tools.py, tests/test_conversations.py, tests/test_list_accounts.py, tests/test_list_categories.py, tests/test_transfers.py, tests/test_agent_suggestions.py, tests/test_agent_cancel.py, app/agent/**, app/services/intents.py
---

# AssistFin — Testes do agente

## Executar

```bash
cd /opt/hosting
docker compose exec -T app2 python -m pytest -q
```

Só agente + finanças relacionadas:

```bash
docker compose exec -T app2 python -m pytest \
  tests/test_intents.py \
  tests/test_transfers.py \
  tests/test_transaction_wizard.py \
  tests/test_transaction_slots.py \
  tests/test_transaction_dates.py \
  tests/test_parse_date.py \
  tests/test_planned_transactions.py \
  tests/test_account_wizard.py \
  tests/test_category_wizard.py \
  tests/test_runner_wizard_escape.py \
  tests/test_list_accounts.py \
  tests/test_list_categories.py \
  tests/test_agent_suggestions.py \
  tests/test_agent_cancel.py \
  tests/test_tools.py \
  -q
```

## Mapa de arquivos

| Arquivo | Cobertura |
|---------|-----------|
| `test_intents.py` | listar vs cadastrar conta/categoria |
| `test_transfers.py` | par, saldos, período sem receita/despesa |
| `test_transaction_wizard.py` | wizard despesa/receita + slots de data |
| `test_transaction_slots.py` | slots (status, datas, conta, categoria) |
| `test_transaction_dates.py` | competência, vencimento, pagamento, orçamento |
| `test_planned_transactions.py` | previsto/realizado, filtro `status`, projeção, `realize_planned` |
| `test_parse_date.py` | `parse_date`, `parse_user_date` |
| `test_account_wizard.py` | wizard conta |
| `test_category_wizard.py` | wizard categoria, normalização nome |
| `test_runner_wizard_escape.py` | `process_message` + escape de wizards |
| `test_list_accounts.py` / `test_list_categories.py` | ferramentas de listagem |
| `test_agent_suggestions.py` | chips |
| `test_agent_cancel.py` | cancelar limpa servidor |
| `test_tools.py` | `try_rule_based_parse` |
| `test_summary.py` | dashboard por período, saldo inicial com data |

## Padrão: mock LLM

```python
with patch("app.agent.runner.call_intent_llm", new_callable=AsyncMock, return_value=(tool, "groq")):
    with patch("app.agent.runner.execute_tool", return_value={...}):
        result = await process_message(db, 1, "mensagem", session={})
```

## Casos obrigatórios

- [ ] Listar contas ≠ cadastrar conta
- [ ] Listar categorias ≠ cadastrar categoria
- [ ] Transferência não entra em receitas/despesas do período
- [ ] Transferência altera saldos das contas
- [ ] Cancelar limpa wizard no servidor
- [ ] `register_transfer` para "transferir X da A para B"
- [ ] Regras resolvem "gastei X" sem LLM

## Referência

[test-matrix.md](test-matrix.md)
