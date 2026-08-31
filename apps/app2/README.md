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

- **Contas** — corrente, poupança, carteira, cartão; saldo inicial com data (`opening_balance_date`)
- **Movimentos** — despesa (`expense`), receita (`income`), **transferência** (par `transfer_out` + `transfer_in`)
- **Previsto vs realizado** — `status` `planned` ou `actual`; realização via `realize_planned`
- **Datas por movimento** — competência (`competence_date`), vencimento (`due_date`), pagamento/realização (`payment_date`); `transaction_date` espelha a data de caixa
- **Categorias** — padrão no seed + cadastro manual; nomes normalizados (primeira letra maiúscula, acentos)
- **Orçamentos** — limite mensal por categoria
- **Dashboard** — visão diária, semanal e mensal com:
  - Receitas e despesas do período (somente `income` / `expense`)
  - Resultado do período (receitas − despesas)
  - Saldo anterior e resultado final (saldos reais das contas)
  - Saldos por conta ao fim do período selecionado

### Regras de transferência

Transferências **não** entram em receitas nem despesas — são movimentos entre contas.

| Efeito | Despesa / Receita | Transferência |
|--------|-------------------|---------------|
| Saldos das contas | Sim | Sim |
| Cards Receitas / Despesas do período | Sim | **Não** |

Uma transferência cria duas linhas vinculadas por `transfer_group_id` (saída na origem, entrada no destino).

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

No assistente, ao lançar movimento o wizard pergunta **realizado ou previsto** e depois as datas:
- **Previsão** → competência e vencimento (duas perguntas).
- **Realizado** → data da realização (replicada em competência e vencimento).

### Assistente de IA

- Balão flutuante em todas as telas autenticadas
- **Chips clicáveis** quando falta resposta do usuário
- Confirmação obrigatória para ações de escrita
- Cancelar limpa estado no servidor (wizards, exclusões pendentes)
- Correção ortográfica leve em descrições e nomes de categoria

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
| `/accounts` | Contas e saldos atuais |
| `/transactions` | Movimentos e formulário manual |
| `/budgets` | Orçamentos |
| `/admin` | Aprovação de usuários (root) |
| `/agent/chat` | Chat HTMX do assistente |
| `/api/health` | Health check (público) |
| `/api/summary` | Resumo JSON (autenticado) |

## Ferramentas do agente

| Ferramenta | Descrição |
|------------|-----------|
| `register_expense` / `register_income` | Novo lançamento (wizard: status + datas + confirmação) |
| `register_transfer` | Transferência entre contas |
| `realize_planned` | Converter previsão em lançamento realizado |
| `update_transaction` | Editar lançamento existente |
| `delete_transaction` | Excluir (par de transferência junto) |
| `update_account` | Editar conta (saldo inicial, data, apelido…) |
| `list_transactions` | Últimos movimentos |
| `list_accounts` / `list_categories` | Listar cadastros |
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

Suite completa no container (`145+` testes):

```bash
docker compose exec -T app2 python -m pytest -q
```

Áreas cobertas: finanças, transferências, dashboard por período, agente, wizards, intents, segurança, onboarding, isolamento multiusuário.

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
  main.py           # FastAPI, middlewares, CSP
  auth.py           # sessão, root, escopo
  models.py         # SQLAlchemy
  schemas.py          # Pydantic, ToolCall, formatação BRL
  routers/          # pages (HTML), api (JSON), auth
  services/         # finance, wizards, tools, intents
  agent/            # runner, llm, groq, ollama, prompt
  security/         # csrf, rate_limit
  templates/        # Jinja2 + partials HTMX
tests/
alembic/
```
