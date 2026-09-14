# Referência — padrões de agentes

## Fontes consultadas

- [Cursor Agent Skills](https://cursor.com/docs/skills) — estrutura SKILL.md, progressive disclosure
- [MLflow — State in AI Agents](https://mlflow.org/articles/state-management-agents/) — híbrido stateful runtime + LLM stateless
- [Agents Arcade — FastAPI LLM apps](https://agentsarcade.com/blog/building-llm-apps-with-fastapi-best-practices) — camada HTTP fina, tools como APIs internas
- [Anthropic — Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) — roteamento, confirmação, loops com limite
- Padrão Agent Skills open standard — `name` + `description` portáveis
- [anthropics/claude-cookbooks — patterns/agents](https://github.com/anthropics/claude-cookbooks/tree/main/patterns/agents) (baixado em 2026-09-14) — implementações de referência de **orchestrator-workers** (um LLM decompõe uma tarefa ampla e delega a chamadas menores) e **evaluator-optimizer** (um segundo passo de LLM critica/valida a saída do primeiro antes de entregar)
- [anthropics/skills](https://github.com/anthropics/skills) (consultado em 2026-09-14) — repositório público de Agent Skills da Anthropic; mesmo formato `SKILL.md` já usado neste projeto (`.cursor/skills/`), confirma que a convenção adotada aqui é compatível com o padrão aberto
- Skill interna `claude-api` deste Claude Code — tabela de modelos/preço Claude, `shared/agent-design.md` (tool surface, memória, cache) e `shared/cost-optimization.md`

## Escalando além do CRUD (agente proativo)

Os padrões abaixo complementam a tabela de roteamento acima quando o agente precisa fazer mais que "escolher ferramenta + preencher slot":

| Padrão | O que é | Quando vale para o AssistFin |
|--------|---------|-------------------------------|
| **Orchestrator-workers** | Um LLM "orquestrador" decompõe um pedido amplo em sub-tarefas e chama ferramentas/LLMs menores para cada uma, agregando o resultado | Pedidos como "revise meus gastos de agosto e sugira cortes" — decompor em `get_summary` + `get_budget_status` + `list_transactions` e sintetizar |
| **Evaluator-optimizer** | Uma segunda chamada de LLM (ou heurística) valida/critica a resposta antes de mostrar ao usuário | Insight financeiro gerado por LLM: validar que nenhum valor foi inventado (comparar contra os números já calculados em Python) antes de exibir |
| **Memória de longo prazo (arquivo/registro)** | Persistir fatos aprendidos sobre o usuário fora do prompt, lidos/escritos de forma controlada (não freeform) | Preferências (categorias recorrentes, metas de orçamento) — estruturado em tabela própria, não em blob de chat |
| **Camada de LLM mais capaz sob demanda** | Modelo barato (Groq/Llama) resolve o caminho comum; um modelo mais forte entra só quando o caminho comum falha ou a tarefa é claramente mais difícil | 3º nível de fallback de NLU; geração de insight/explicação em linguagem natural; orquestração multi-etapas |

Anti-padrão adicional: deixar o LLM "mais inteligente" escrever memória ou insight livre sem os mesmos dois anti-padrões do topo do arquivo (LLM não calcula valores; sem confirmação não escreve) — a evolução para "inteligência proativa" **não** relaxa essas duas regras, só adiciona um novo tipo de leitura (explicação/sugestão) que passa pelo mesmo funil de confirmação para qualquer escrita.

Plano concreto de aplicação: [`.cursor/plans/agente-inteligencia-proativa.md`](../../plans/agente-inteligencia-proativa.md).

## Mapeamento AssistFin → padrão

| Padrão | Implementação atual |
|--------|---------------------|
| Router | `runner.py` + `intents.py` + `transaction_slots.py` + `transfer_slots.py` |
| Tools | `tools.py` + `finance.py` |
| Checkpointer | `session` + wizard keys (`transfer_wizard`, etc.) |
| Episodic log | `conversations.py` |
| Evaluator | confirmação HTMX + chips (fora do balão) |
| Fallback model | Groq → `try_rule_based_parse` |

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
