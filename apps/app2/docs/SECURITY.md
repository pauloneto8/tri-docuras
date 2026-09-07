# Segurança — AssistFin

## Autenticação e sessão

- Senhas hasheadas com **bcrypt** (`app/auth.py`)
- Cookie de sessão `financas_session`, assinado com `APP2_SECRET_KEY`
- Validade: 7 dias; `SameSite=lax`
- `SECRET_KEY` obrigatória — app não inicia com valor default inseguro (`app/config.py`)
- Middleware redireciona não autenticados para `/login` (HTML) ou 401 (API)

## Autorização

- `require_user` — rotas autenticadas
- `require_root` — `/admin` e ações administrativas (aprovação de usuários, backup/restauração do banco)
- Novos cadastros: `is_active=false` até aprovação root
- Onboarding middleware bloqueia app até primeira conta configurada

## CSRF

- Token em `session["csrf_token"]` para usuários logados
- Validado em POST sensíveis (logout, onboarding, admin, **importação de extrato** cartão/conta)
- Comparação com `secrets.compare_digest` (timing-safe)

## Rate limiting

- **Aplicação**: `check_rate_limit` em login (`app/security/rate_limit.py`)
- **Nginx**: `limit_req zone=auth_limit` em `/login` e `/register` (5 req/min)
- Buckets em memória (instância única)

## Headers HTTP

Definidos em `app/main.py` e espelhados no Nginx:

- `Content-Security-Policy` — scripts CDN permitidos (Tailwind, HTMX)
- `X-Frame-Options: DENY`
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: strict-origin-when-cross-origin`

## Rede e infraestrutura

- **PostgreSQL** apenas em `app2_internal`
- **TrustedHostMiddleware** — rejeita Host inválido
- App roda como `appuser` no container (não root)
- OpenAPI/docs **desabilitados** (`docs_url=None`)
- LLM externo: **Groq** via HTTPS (chave em `APP2_GROQ_API_KEY`)

## Dados sensíveis

- Nunca commitar `.env`, `APP2_SECRET_KEY`, `APP2_GROQ_API_KEY`
- Permissão recomendada no `.env`: `chmod 600`
- Health check não expõe versões internas ou credenciais
- Extratos OFX/CSV/PDF/Flash: processados em memória/staging por usuário; **não** armazenam PAN; limite de upload na app **10 MB** (Nginx `client_max_body_size` pode ser menor — tipicamente 1m; aumente se for importar PDF/CSV grandes)

## Isolamento de dados

- Todas as entidades financeiras têm `user_id` FK
- Queries de negócio filtram por usuário logado
- Lotes OFX (`ofx_import_batches`) e linhas amarrados a `user_id` + `card_id` ou `account_id` do dono
- FITID único por usuário (`uq_transactions_user_ofx_fitid`) evita reimportação duplicada
- Testes de isolamento em `tests/test_isolation.py`

## Chat / agente

- Confirmação obrigatória antes de persistir lançamentos
- LLM não recebe senhas nem executa SQL direto
- Ferramentas validadas por Pydantic antes de `execute_tool`
- Logs de conversa para auditoria (sem dados de cartão — app não armazena PAN)
- Mensagens do assistente passam por `chat_md`: HTML escapado antes de negrito/listas (XSS)
- Importação de extrato é **somente UI** (sem ferramenta de chat na v1)

## Checklist de deploy seguro

- [ ] `APP2_SECRET_KEY` forte e única
- [ ] `APP2_ALLOW_REGISTRATION` conforme política desejada
- [ ] `APP2_GROQ_API_KEY` configurada
- [ ] HTTPS quando em produção pública (Let's Encrypt via `issue-certs.sh`)
- [ ] Testes passando após deploy
- [ ] Nginx `client_max_body_size` adequado para upload de extrato (app aceita até **10 MB**)
