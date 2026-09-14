# Plano: dar inteligência proativa ao agente do AssistFin

**Status:** Fase 1 (fundação) e Fase 2 (insight proativo) implementadas em 2026-09-14, feature flag `ENABLE_AI_INSIGHTS` desligada até validar em conta de teste. Fases 3-5 seguem propostas.
**Workspace:** `/opt/hosting/apps/app2`
**Origem:** pedido do usuário — evoluir o assistente de "executor de CRUD financeiro via Groq" para um agente com (1) entendimento de linguagem mais livre, (2) memória de longo prazo/personalização, (3) insights e conselhos financeiros proativos, (4) raciocínio multi-etapas.

Antes de editar: `move_agent_to_root` → `/opt/hosting/apps/app2`.
Ler primeiro: [`.cursor/skills/assistfin-ai-agent/SKILL.md`](../skills/assistfin-ai-agent/SKILL.md), [`.cursor/skills/ai-agent-design-patterns/SKILL.md`](../skills/ai-agent-design-patterns/SKILL.md) + [`patterns-reference.md`](../skills/ai-agent-design-patterns/patterns-reference.md) (seção "Escalando além do CRUD"), [`.cursor/skills/assistfin-finance-domain/SKILL.md`](../skills/assistfin-finance-domain/SKILL.md).
Responder em **português**.

---

## Estado atual (o que já existe, não mexer sem necessidade)

Arquitetura híbrida já documentada em `assistfin-ai-agent`: LLM stateless (Groq, `openai/gpt-oss-120b`) escolhe ferramenta → runtime stateful (sessão + wizards) coleta slots → `execute_tool()` em Python executa e nunca deixa o modelo calcular saldo. Já existem `get_summary`, `get_budget_status` e `categorize` como ferramentas de leitura — base pronta para construir insights em cima, sem precisar dar acesso de escrita a um novo modelo.

Isso já é "inteligente" para o caso de uso original (lançar e consultar). O que falta é o agente **falar primeiro** (insight proativo), **lembrar** entre sessões, e **decompor pedidos amplos** — coisas que Groq/Llama fazem pior que Claude em tarefas de raciocínio mais longo, mas que não precisam rodar em toda mensagem.

## Decisão principal: dois modelos, cada um no que faz melhor

| Camada | Modelo | Por quê |
|--------|--------|---------|
| Roteamento/tool-calling de toda mensagem (já existe) | Groq `openai/gpt-oss-120b` | Rápido, já pago, já testado — não trocar o caminho comum |
| Insight proativo, explicação, fallback de NLU difícil, orquestração multi-etapas (novo) | Claude (`claude-haiku-4-5` por padrão; `claude-sonnet-5` só no orquestrador sob demanda explícita) | Melhor raciocínio para "explicar" e "planejar"; usado **seletivamente**, não em toda mensagem, para manter custo baixo em um VPS único |

Regra geral (herdada do anti-padrão já documentado): **nenhum dos dois modelos calcula dinheiro**. Claude só recebe números que o Python já calculou (`get_summary`, `get_budget_status`) e explica/soma contexto; nunca gera `amount` ou saldo.

Custo estimado (Haiku 4.5, US$1/US$5 por MTok): 1 insight diário por usuário ≈ 1–2K tokens de entrada + ~300 de saída ≈ US$0,003/usuário/dia — desprezível mesmo com centenas de usuários. Sonnet só quando o usuário pede algo amplo explicitamente, então o custo mais alto é raro e sob controle.

## Fora de escopo (por agora)

- Trocar o roteamento de toda mensagem de Groq para Claude (custo/latência não justificam — Groq já resolve bem o caminho comum).
- Dar ao Claude acesso direto de escrita (`register_*`, `update_*`, `delete_*`). Qualquer ação sugerida por ele passa pelo mesmo funil `needs_confirmation` que já existe.
- Ferramenta de memória de arquivo da Anthropic (`memory_20250818`) — não se encaixa na arquitetura (runtime já é stateful em Postgres/sessão); preferir tabela própria.
- RAG com embeddings/vetores — o volume de dados por usuário (transações de uma pessoa) é pequeno o bastante para caber direto no prompt via `get_summary`/`list_transactions`; não precisa de busca vetorial.

## Fases

### Fase 1 — Fundação (baixo risco) — implementada

`app/config.py` (sem `anthropic_model_reasoning` ainda — só entra na Fase 5) + `app/agent/claude.py`.

- `app/config.py`: `anthropic_api_key: str = ""`, `anthropic_model_fast: str = "claude-haiku-4-5"`, `anthropic_model_reasoning: str = "claude-sonnet-5"`, `enable_ai_insights: bool = False` (feature flag, default off em produção até validar).
- `app/agent/claude.py` (novo, paralelo a `app/agent/groq.py`): cliente Anthropic, função `call_claude(system, messages, model, max_tokens)` com tratamento de erro igual ao padrão já usado em `groq.py`/`llm.py`.
- Sem mudança de comportamento visível — só infraestrutura.

### Fase 2 — Insight proativo (a capacidade mais visível, risco baixo) — implementada

`app/models.py` (`AgentInsight`) + migração `020_agent_insights.py` + `app/services/insights.py` + `app/scripts/generate_insights.py` (CLI para cron) + exibição em `agent_welcome` (`pages.py`). Validação: nenhum LLM extra — checagem em Python que todo valor `R$ x,xx` citado no texto é um dos valores enviados no prompt.

- Nova tabela `agent_insights` (migração `alembic/versions/020_agent_insights.py`): `id, user_id, year, month, text, created_at`.
- Job diário/mensal (endpoint interno chamado por cron do host, mesmo padrão do backup em `docs/OPERATIONS.md`) que, por usuário ativo: chama `get_summary` + `get_budget_status` já existentes, monta um prompt curto só com os números, chama Claude Haiku pedindo um insight de 2–3 frases em português, valida (evaluator simples: nenhum número no texto pode divergir dos números de entrada — checagem em Python, não outro LLM) e salva.
- Exibir no dashboard / mensagem de boas-vindas do chat (`agent_assistant_message.html`), com `source=claude` gravado em `conversation_messages` para auditoria (mesmo padrão já usado para `source=rule|wizard|groq`).

### Fase 3 — Fallback de NLU mais livre (risco baixo)

- Em `runner.py`, quando Groq **e** `try_rule_based_parse` falham (hoje cai direto em `unsupported_action`), tentar uma vez o Claude Haiku com o mesmo `SYSTEM_PROMPT` de ferramentas antes de desistir. Mantém o formato `ToolCall` único — é só mais um nível na cadeia barato→caro já documentada em `ai-agent-design-patterns`.

### Fase 4 — Memória de personalização (médio risco, precisa de design)

- Tabela `user_agent_preferences` (chave/valor estruturado — ex.: `categoria_favorita_supermercado`, `meta_orcamento_lazer`), **não** texto livre.
- Escrita só por caminhos determinísticos já existentes (ex.: se o usuário confirma uma categorização repetida 3x, salvar preferência) ou confirmação explícita — nunca o LLM decidindo sozinho o que "lembrar".
- Leitura: injetar só os poucos pares relevantes no prompt (Groq e Claude), como contexto curto — mesmo princípio de "memória de working state fora do prompt, injeção curta" já na skill.

### Fase 5 — Orquestrador multi-etapas (maior risco/custo, só sob demanda explícita)

- Detectar no runner pedidos amplos que não mapeiam a nenhuma ferramenta única (heurística: mensagem longa + verbos como "revise", "organize", "analise" sem valor/conta claros).
- Rodar um Tool Runner do Claude (`client.beta.messages.tool_runner`, ver skill `claude-api`) com Sonnet, `effort: medium`, limite de turnos (ex.: 5), expondo **somente** as ferramentas de leitura já existentes (`list_transactions`, `get_summary`, `get_budget_status`, `list_categories`, `list_invoices`) como tools do Claude.
- Qualquer ação de escrita que o orquestrador queira sugerir vira uma proposta em texto ("quer que eu categorize essas 12 transações como Lazer?") que, se o usuário aceitar, é traduzida para os `ToolCall` de escrita já existentes e passa pela confirmação normal — o orquestrador nunca escreve direto.

## Guardrails (valem para todas as fases)

- LLM nunca calcula saldo, valor ou data crítica — só o Python (regra já existente, mantida).
- Toda escrita passa por `needs_confirmation`, inclusive as sugeridas por Claude.
- Gravar `source` (`claude-insight`, `claude-fallback`, `claude-orchestrator`) em `conversation_messages`/`agent_insights` para auditoria e para medir se compensa (mesma métrica de "Groq vs rule" já sugerida na skill de padrões).
- Feature flag por fase — ativar Fase 2 antes de mexer na Fase 5.
- Nunca enviar dados financeiros brutos de todos os usuários numa chamada só; sempre por usuário, com os números já agregados em Python.

## Arquivos a alterar (visão geral — detalhar por fase quando for implementar)

| Arquivo | O quê |
|---------|-------|
| `app/config.py` | Novas settings (`anthropic_api_key`, modelos, feature flags) |
| `app/agent/claude.py` (novo) | Cliente Claude, paralelo a `groq.py` |
| `app/agent/runner.py` | Fallback de 3º nível (Fase 3); detecção de pedido amplo → orquestrador (Fase 5) |
| `alembic/versions/020_agent_insights.py` (novo) | Tabela `agent_insights` |
| `alembic/versions/021_user_agent_preferences.py` (novo) | Tabela `user_agent_preferences` |
| `app/services/insights.py` (novo) | Geração + validação de insight diário/mensal (Fase 2) |
| `app/templates/partials/agent_assistant_message.html` | Exibir insight proativo |
| `docs/ARCHITECTURE.md`, `docs/OPERATIONS.md`, `docs/CHANGELOG.md`, `.cursor/skills/assistfin-ai-agent/SKILL.md` | Documentar o novo cliente Claude, a tabela de insights e o job de cron |
| `.env` / `docker-compose.yml` do app2 | Nova variável `ANTHROPIC_API_KEY` (segredo — não commitar valor) |

## Próximo passo

Plano aprovado → começar pela **Fase 1 + Fase 2** (fundação + insight proativo), que é a parte mais visível e de menor risco, com a feature flag desligada até validar em conta de teste.
