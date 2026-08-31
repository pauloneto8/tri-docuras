---
name: ai-agent-design-patterns
description: >-
  Padrões de design para agentes de IA em produção: roteamento, memória,
  ferramentas, confirmação e fallbacks LLM. Use ao projetar novas capacidades
  do assistente, refatorar runner, adicionar ferramentas ou melhorar
  compreensão de intenção no AssistFin ou apps similares.
---

# Padrões de agentes de IA (aplicados ao AssistFin)

Baseado em práticas de Anthropic, LangGraph, MLflow e FastAPI para apps LLM (2025–2026).

## 1. Orquestrador fino, ferramentas grossas

- Endpoints HTTP validam auth e delegam a `process_message`.
- LLM **só** escolhe ferramenta + extrai slots; cálculos ficam em código Python.
- Cada ferramenta: schema Pydantic, testes, mensagem de erro clara.

## 2. Roteamento em camadas (barato → caro)

```
1. Cancelamento / comandos fixos
2. Estado de wizard (continuação)
3. Heurísticas determinísticas (regex, keywords)
4. LLM remoto rápido (Groq) para ambiguidade
5. LLM local (Ollama) como fallback
```

Nunca pular para LLM se regra ou wizard resolver com confiança.

## 3. Memória em quatro níveis

| Nível | AssistFin hoje | Uso |
|-------|----------------|-----|
| Working | última mensagem + wizard session | passo atual |
| Session | `session` Starlette | wizards, flags login |
| Episódico | `conversation_messages` | debug, auditoria |
| Semântico | (futuro) | preferências do usuário |

Persistir estado do wizard **fora** do prompt; injetar só contexto curto ao LLM.

## 4. Confirmação para ações irreversíveis

- Escritas (`register_*`, `create_account`, `register_transfer`) → `needs_confirmation`.
- Leituras (`list_*`, `get_summary`) → executar direto.
- Wizard coleta dados; confirmação final antes de persistir.

## 5. Intenção vs slot-filling

- **Intenção errada** (ex.: listar contas vs cadastrar) → sair do wizard e re-rotear.
- **Slot errado** (valor inválido) → repetir pergunta do mesmo passo.
- **Slots condicionais** (ex.: datas de transação) → ordem fixa no código (`_next_slot`), não no LLM; previsto pede competência + vencimento; realizado pede data da realização.
- Não misturar: delegação ao LLM só quando a intenção mudou.

## 6. Prompt de ferramentas

- Uma ferramenta por resposta JSON.
- Listar ferramentas com exemplos de quando usar cada uma.
- Proibir comportamentos conhecidos (`list_accounts` quando pediu contas).
- `temperature` baixa (0.1); JSON mode quando disponível.

## 7. Observabilidade

- Gravar `source` (`rule`, `wizard`, `groq`, `ollama`) no fluxo.
- Logar user + assistant em `conversation_messages`.
- Reproduzir bugs lendo conversas antes de adicionar regex.

## 8. Anti-padrões

- LLM calcular saldos ou datas críticas.
- Wizard sem saída para intenção alternativa.
- Reiniciar wizard e perder dados já coletados sem motivo.
- Uma única heurística "conta" para listar e cadastrar.

## Aplicar no AssistFin

Ao adicionar capacidade nova:

1. Definir se é leitura ou escrita.
2. Adicionar `ToolCall` + teste de regra mínima.
3. Atualizar `intents.py` se colidir com wizard.
4. Atualizar prompt Groq/Ollama.
5. Teste de conversa real (casos do DB).

Mais detalhes: [patterns-reference.md](patterns-reference.md)
