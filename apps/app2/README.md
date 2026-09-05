# AssistFin

Aplicação web multiusuário de **finanças pessoais** com assistente de IA (Groq + Ollama), deploy em Docker na infraestrutura `/opt/hosting`.

## Stack

| Camada | Tecnologia |
|--------|------------|
| Backend | FastAPI, SQLAlchemy 2, Alembic, Pydantic |
| Banco | PostgreSQL 16 (`hosting-app2-db`) |
| IA | Groq (prioridade) + Ollama `qwen3:1.7b` (fallback) |
| UI | Jinja2, HTMX, Tailwind CDN |
| Auth | Sessão assinada (cookie), bcrypt |
| Proxy | Nginx (`hosting-nginx`) |

## Infraestrutura

```
Internet :80/:443
  └── hosting-nginx (rede proxy)
        └── hosting-app2 :8000
              ├── hosting-app2-db (rede app2_internal)
              └── hosting-ollama (rede app2_internal — não exposto)
```

- Código: `/opt/hosting/apps/app2`
- Compose: `/opt/hosting/docker-compose.yml`
- Container da app: usuário `appuser` (não root)
- Migrações automáticas no `entrypoint.sh` (`alembic upgrade head`)

## Funcionalidades

### Finanças

- **Contas** — corrente, poupança, carteira; saldo inicial com data (`opening_balance_date`)
- **Cartões de crédito** — entidade própria (`credit_cards`), separada das contas bancárias; fechamento, vencimento, limite e conta de liquidação obrigatória no cadastro
- **Movimentos** — despesa (`expense`), receita (`income`), **transferência** (par `transfer_out` + `transfer_in`); tela em duas seções (**A realizar** / **Extrato**); cada movimento referencia **conta** e/ou **cartão**
- **Previsto vs realizado** — `status` `planned` ou `actual`; realização via `realize_planned` (UI e wizard no assistente)
- **Lançamentos fixos** — recorrência diária, semanal ou mensal; gera previstos automaticamente (~3 meses à frente); encerrar série remove pendentes
- **Lançamentos parcelados** — parcelas mensais/semanais/quinzenais; valor total ou por parcela; parcela inicial parcial; datas de competência/vencimento no wizard; cancelar plano remove previstos pendentes
- **Cartões de crédito** — faturas por ciclo; compras no cartão não alteram saldo bancário; pagamento da fatura como despesa na conta de débito (sem duplicar despesa da compra)
- **Datas por movimento** — competência (`competence_date`), vencimento (`due_date`), pagamento/realização (`payment_date`); `transaction_date` espelha a data de caixa
- **Categorias** — padrão no seed + cadastro manual; nomes normalizados (primeira letra maiúscula, acentos)
- **Orçamentos** — limite mensal por categoria
- **Dashboard** — visão diária, semanal e mensal com:
  - Receitas e despesas do período (somente `income` / `expense`)
  - Resultado do período (receitas − despesas)
  - Saldo anterior e resultado final (saldos reais das contas)
  - Saldos por conta ao fim do período selecionado
  - **Faturas dos cartões** — total a pagar, vencimento no período, limite disponível (compras no cartão não entram no saldo bancário)

### Regras de transferência

Transferências **não** entram em receitas nem despesas — são movimentos entre contas.

| Efeito | Despesa / Receita | Transferência |
|--------|-------------------|---------------|
| Saldos das contas | Sim | Sim |
| Cards Receitas / Despesas do período | Sim | **Não** |

Uma transferência cria duas linhas vinculadas por `transfer_group_id` (saída na origem, entrada no destino). Para **corrigir** origem, destino, valor ou data de um par já lançado, use `update_transfer` — não `update_transaction`.

### Datas e previsto vs realizado

| Papel | Campo | Previsto (`planned`) | Realizado (`actual`) |
|-------|--------|----------------------|----------------------|
| Competência (orçamento) | `competence_date` | Sim | Sim |
| Vencimento / projeção | `due_date` | Sim | Igual à realização |
| Caixa (saldo) | `payment_date` | `NULL` | Obrigatório |
| Data de caixa no sistema | `transaction_date` | = `due_date` | = `payment_date` |

- **Orçamentos** somam despesas pela **competência**, não pela data de pagamento.
- **Saldos** consideram só movimentos **realizados** (`status = actual`), pela data de caixa.
- **Previstos pendentes** entram na projeção do dashboard pelo vencimento.

No assistente, ao lançar movimento o wizard pergunta **realizado ou previsto**, depois se é **único**, **fixo** ou **parcelado**, e em seguida as datas:
- **Previsão** (não parcelado) → competência e vencimento (duas perguntas), depois o modo.
- **Realizado** (não parcelado) → modo primeiro (se ainda indefinido), depois data da realização (replicada em competência e vencimento).
- **Fixo** → frequência (diária/semanal/mensal) e término opcional; gera série de previstos.
- **Parcelado** → N parcelas, intervalo, parcela inicial, competência e vencimento da parcela atual; gera só da parcela informada até N.

Na página **Movimentos** (`/transactions`), o formulário manual segue a mesma lógica:
- **A realizar** — previstos pendentes (vencimento; selo `Fixo · …` quando recorrente; selo `3/12 · mensal` quando parcelado; ações **Realizar**, **Encerrar série** e **Cancelar parcelas**).
- **Extrato** — somente realizados (data de pagamento; “de previsto” quando aplicável).
- Previstos já liquidados não aparecem na lista (o par previsto/realizado fica no dashboard).

**Realizar previsto:** na UI, escolha mesma conta ou outra conta; no assistente, wizard pergunta pagamento → mesma conta? → conta (se diferente).

### Lançamentos fixos (recorrência)

| Aspecto | Comportamento |
|---------|---------------|
| Frequências | Diária, semanal, mensal |
| Horizonte | Previstos gerados até `min(data_término, hoje + 3 meses)` |
| Primeira ocorrência | Segue o status informado (`planned` ou `actual`) |
| Demais ocorrências | Sempre `planned` |
| Realizar uma ocorrência | Não encerra a série; reabastece o horizonte |
| Encerrar série | Desativa a regra; remove previstos pendentes (realizados permanecem) |
| Transferências | Não suportam recorrência |

Motor: `app/services/recurrence.py` (`ensure_recurring_horizon`, `deactivate_recurring_rule`).

### Lançamentos parcelados

| Aspecto | Comportamento |
|---------|---------------|
| Intervalos | Mensal, semanal, quinzenal |
| Valor | Total da compra (÷ N; resto na última) **ou** valor de cada parcela (× N) — wizard e formulário |
| Parcela inicial | Pergunta qual parcela está sendo lançada (1…N); gera só da informada até a última |
| Competência / vencimento | Perguntados no wizard **no contexto da parcela**; vencimento ancora o cronograma |
| Realizado + parcelado | `payment_date` (caixa) é independente de competência/vencimento |
| Primeira parcela gerada | A de `installment_start_index` segue o status informado (`planned` ou `actual`) |
| Demais parcelas geradas | Sempre `planned` |
| Inferência de datas | `ontem`/`hoje` na mensagem **não** substituem perguntas do parcelamento |
| Cancelar parcelas | Desativa o plano; remove previstos pendentes (realizados permanecem) |
| Transferências / fixo | Não suportam parcelamento |

Motor: `app/services/installments.py` (`split_cents`, `repeat_cents`, `create_installment_plan`, `cancel_installment_plan`).

`list_transactions` aceita filtro `status` (`actual` | `planned` | `all`).

No wizard, datas isoladas (`10/08/2026`, `hoje`, etc.) preenchem o slot em andamento — **não** disparam multi-lançamentos. No parcelamento, escolher *parcelado* limpa datas genéricas preenchidas antes.

### Assistente de IA

- Balão flutuante em todas as telas autenticadas
- Avatares (assistente à esquerda, inicial do usuário à direita); chips e Confirmar/Cancelar **fora** do balão
- Markdown leve nas respostas (`*negrito*`, listas `- `) via filtro Jinja `chat_md` (HTML escapado)
- **Chips clicáveis** quando falta resposta do usuário; welcome com atalhos
- Confirmação obrigatória para ações de escrita
- Cancelar limpa estado no servidor (wizards, exclusões pendentes)
- Correção ortográfica leve em descrições e nomes de categoria
- Intenção: atalhos de regra para despesa/receita/realizar previsto/pagar fatura; demais pedidos via Groq, com Ollama e regras como fallback

### Multiusuário e acesso

- Registro em `/register` (controlado por `APP2_ALLOW_REGISTRATION`)
- Novos usuários ficam **inativos** até aprovação do admin root
- Root: e-mails em `APP2_ROOT_EMAILS` (padrão `pauloneto8@gmail.com`)
- Onboarding obrigatório na primeira conta principal
- Dados isolados por `user_id`

## Rotas principais

| Rota | Descrição |
|------|-----------|
| `/login`, `/register` | Autenticação |
| `/onboarding` | Primeira conta (apelido + saldo inicial + data) |
| `/` | Dashboard com visão por período |
| `/accounts` | Contas bancárias e saldos atuais |
| `/accounts/cards` | Cartões de crédito (cadastro, faturas, pagar fatura) |
| `/transactions` | Movimentos: **A realizar**, **Extrato**, formulário manual e encerrar série |
| `/budgets` | Orçamentos |
| `/admin` | Aprovação de usuários (root) |
| `/agent/chat` | Chat HTMX do assistente |
| `/api/health` | Health check (público) |
| `/api/summary` | Resumo JSON (autenticado) |

## Ferramentas do agente

| Ferramenta | Descrição |
|------------|-----------|
| `register_expense` / `register_income` | Novo lançamento (wizard: status → modo → parcelas/datas/valor → confirmação); `installment_count`, `installment_interval`, `installment_start_index`, `installment_amount_basis` perguntados pelo sistema — **não** enviar pelo LLM |
| `register_transfer` | Transferência entre contas |
| `update_transfer` | Corrigir transferência existente (origem, destino, valor ou data — **não** usar `update_transaction`) |
| `realize_planned` | Converter previsão em realizado (wizard: pagamento, mesma/outra conta) |
| `update_transaction` | Editar despesa/receita existente |
| `delete_transaction` | Excluir (par de transferência junto) |
| `update_account` | Editar conta bancária (saldo inicial, data, apelido…) |
| `create_card` | Cadastrar cartão (wizard: apelido, fechamento, vencimento, conta de liquidação…) |
| `update_card` | Editar cartão (apelido, instituição, limite, fechamento, vencimento, liquidação) |
| `delete_card` | Excluir cartão (desativação lógica; histórico preservado) |
| `list_invoices` | Listar faturas de cartão |
| `pay_invoice` | Pagar fatura (despesa na conta de débito) |
| `list_transactions` | Últimos movimentos (`limit`, `type`, `status`) |
| `list_accounts` / `list_categories` | Listar cadastros (contas **e** cartões em `list_accounts`) |
| `get_summary` | Resumo financeiro |
| `get_budget_status` | Status dos orçamentos |
| `create_account` / `create_category` | Cadastros via wizard |
| `categorize` | Sugestão de categoria por palavras-chave |
| `unsupported_action` | Pedido fora do escopo |

## Variáveis de ambiente

| Variável | Descrição |
|----------|-----------|
| `APP2_SECRET_KEY` | Chave da sessão (**obrigatória** em produção) |
| `APP2_ALLOW_REGISTRATION` | `true`/`false` — registro público |
| `APP2_ROOT_EMAILS` | E-mails admin (vírgula) |
| `APP2_GROQ_API_KEY` | API Groq (intenção ambígua) |
| `APP2_GROQ_MODEL` | Modelo Groq (default `openai/gpt-oss-120b`) |
| `APP2_DOMAIN` | Domínio no Nginx + `TRUSTED_HOSTS` |
| `OLLAMA_URL` / `OLLAMA_MODEL` | LLM local de fallback |

## Segurança

- Sessão assinada com `SECRET_KEY`; cookie `financas_session` (7 dias, SameSite=lax)
- **CSRF** em formulários POST (logout, onboarding, admin)
- **Rate limit** no login (app + Nginx `auth_limit`)
- **TrustedHostMiddleware** — hosts permitidos via `TRUSTED_HOSTS`
- Headers: CSP, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`
- OpenAPI/Swagger **desabilitados** em produção
- Ollama apenas na rede interna Docker
- Senhas com bcrypt; comparação timing-safe no CSRF
- Health check mínimo (sem vazar dados internos)

Detalhes: [docs/SECURITY.md](docs/SECURITY.md)

## Desenvolvimento e deploy

```bash
cd /opt/hosting
docker compose build app2
docker compose up -d app2
docker compose exec -T app2 python -m pytest -q
```

Recarregar Nginx (se alterou domínio/template):

```bash
./scripts/reload-nginx.sh
```

Operações (reset de dados, migrações, debug): [docs/OPERATIONS.md](docs/OPERATIONS.md)

## Testes

Suite completa no container (**246** testes):

```bash
docker compose exec -T app2 python -m pytest -q
```

Áreas cobertas: finanças, transferências (incluindo `update_transfer`), previstos/realizados, recorrência, parcelas, cartões de crédito, dashboard por período, agente (LLM-first + wizards), formatação do chat (`chat_md`), wizards (transação, cartão, realizar previsto, fatura), multi-lançamentos vs datas, intents, segurança, onboarding, isolamento multiusuário.

## Migrações (Alembic)

| Revisão | Conteúdo |
|---------|----------|
| 001 | Schema inicial |
| 002 | Multiusuário (`user_id`) |
| 003 | Campos bancários + saldo inicial |
| 004 | Logs de conversa |
| 005 | `is_root` |
| 006 | Aprovação de usuários |
| 007 | Onboarding |
| 008 | `opening_balance_date` |
| 009 | Normalização de nomes de categorias |
| 010 | Transferências (`transfer_group_id`, tipos) |
| 011 | Previsto vs realizado (`status`, `source_planned_id`) |
| 012 | Competência, vencimento e pagamento (`competence_date`, `due_date`, `payment_date`) |
| 013 | Lançamentos fixos (`recurring_rules`, `recurrence_id`) |
| 014 | Lançamentos parcelados (`installment_plans`, `installment_plan_id`, `installment_index`) |
| 015 | Faturas de cartão (`card_invoices`, `transactions.invoice_id`) |
| 016 | Entidade `credit_cards` separada de contas; `transactions.card_id`; migração de contas `cartao` legadas |

## Documentação para o Cursor

| Arquivo | Uso |
|---------|-----|
| [AGENTS.md](AGENTS.md) | Guia para agentes de IA no repositório |
| `.cursor/skills/` | Skills por domínio (finanças, agente, deploy, testes…) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Arquitetura e fluxos |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Operações e manutenção |
| [docs/SECURITY.md](docs/SECURITY.md) | Segurança |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | Evoluções recentes |

## Estrutura do código

```
app/
  main.py           # FastAPI, middlewares, CSP, filtro chat_md
  chat_format.py    # markdown leve e seguro das mensagens do assistente
  auth.py           # sessão, root, escopo
  models.py         # SQLAlchemy
  schemas.py        # Pydantic, ToolCall, formatação BRL
  routers/          # pages (HTML), api (JSON), auth
  services/         # finance, recurrence, installments, credit_cards, wizards, tools, intents
  agent/            # runner, llm, groq, ollama, prompt
  security/         # csrf, rate_limit
  templates/        # Jinja2 + partials HTMX (agent_*.html)
tests/
alembic/
```
