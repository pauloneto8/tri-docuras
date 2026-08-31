# Referência — padrões de agentes

## Fontes consultadas

- [Cursor Agent Skills](https://cursor.com/docs/skills) — estrutura SKILL.md, progressive disclosure
- [MLflow — State in AI Agents](https://mlflow.org/articles/state-management-agents/) — híbrido stateful runtime + LLM stateless
- [Agents Arcade — FastAPI LLM apps](https://agentsarcade.com/blog/building-llm-apps-with-fastapi-best-practices) — camada HTTP fina, tools como APIs internas
- [Anthropic — Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) — roteamento, confirmação, loops com limite
- Padrão Agent Skills open standard — `name` + `description` portáveis

## Mapeamento AssistFin → padrão

| Padrão | Implementação atual |
|--------|---------------------|
| Router | `runner.py` + `intents.py` + `transaction_slots.py` + `transfer_slots.py` |
| Tools | `tools.py` + `finance.py` |
| Checkpointer | `session` + wizard keys (`transfer_wizard`, etc.) |
| Episodic log | `conversations.py` |
| Evaluator | confirmação HTMX + chips |
| Fallback model | Groq → Ollama |

## Template para nova ferramenta

```python
# schemas.py — adicionar ao Literal de ToolCall
# tools.py — try_rule_based_parse (se padrão óbvio)
# tools.py — execute_tool + format_tool_result
# prompt.py — documentar no SYSTEM_PROMPT
# tests/test_tools.py ou test dedicado
```

## Métricas de qualidade do agente

- Taxa de wizard travado (conversas repetindo mesma pergunta)
- `source=groq` vs `source=rule` (custo vs acerto)
- Confirmações canceladas vs concluídas
- Erros `ValidationError` pós-LLM
