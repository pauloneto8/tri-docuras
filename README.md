# Hosting — VPS

Infraestrutura Docker para hospedar duas aplicações isoladas, com Nginx como proxy reverso por domínio.

## Arquitetura

```
Internet :80/:443
    └── nginx (hosting-nginx)
            ├── tridocuras.com.br → app1-web (Flutter) + /api → app1 (Dart Frog)
            └── assistfin.com.br  → app2 (AssistFin + agente IA)
```

Cada app tem stack isolada: container web/API, PostgreSQL dedicado, rede interna e volume de dados próprios.

## Estrutura

```
/opt/hosting/
├── .env                    # domínios, credenciais de banco, e-mail Certbot
├── docker-compose.yml
├── nginx/                  # templates e SSL
├── apps/
│   ├── app1/               # Tri Doçuras (Flutter + Dart Frog)
│   └── app2/               # AssistFin (FastAPI + agente IA)
├── certs/                  # Let's Encrypt
├── scripts/
│   ├── reload-nginx.sh
│   └── issue-certs.sh
└── README.md
```

## Domínios (`.env`)

| Variável | Valor | Uso |
|----------|-------|-----|
| `APP1_DOMAIN` | `tridocuras.com.br` | Tri Doçuras |
| `APP2_DOMAIN` | `assistfin.com.br` | AssistFin |

## Comandos úteis

```bash
cd /opt/hosting

# Status de todos os serviços
docker compose ps

# Subir tudo
docker compose up -d

# Health rápido
curl -s https://tridocuras.com.br/api/health
curl -s https://assistfin.com.br/health

# Rebuild Tri Doçuras
docker compose build app1 app1-web && docker compose up -d app1 app1-web

# Rebuild AssistFin
docker compose build app2 && docker compose up -d app2

# Logs
docker compose logs -f app1 app1-web app2 nginx

# Recarregar Nginx após mudar domínio no .env
./scripts/reload-nginx.sh
```

## HTTPS

Certificados Let's Encrypt em `/opt/hosting/certs`. Renovação via profile `certbot` ou scripts em `scripts/`.

1. Edite `APP1_DOMAIN` / `APP2_DOMAIN` e `CERTBOT_EMAIL` no `.env`
2. Aponte os registros **A** dos domínios ao IP do servidor
3. `./scripts/reload-nginx.sh`
4. `./scripts/issue-certs.sh` (quando aplicável)

## Firewall (UFW)

Expor apenas `80`, `443` e SSH conforme a política do provedor.

---

## Tri Doçuras (App 1)

**URL:** https://tridocuras.com.br

| Container | Função |
|-----------|--------|
| `hosting-app1-web` | Flutter web (Nginx estático) |
| `hosting-app1` | API Dart Frog (`/api/*`) |
| `hosting-app1-db` | PostgreSQL 16 |

Fluxo de compra completo (6 telas): catálogo → produto → carrinho → checkout → Pix → confirmação. Pedidos e pagamento Pix integrados ao backend (Mercado Pago). Credenciais em `APP1_MP_*` no `.env`.

```bash
docker compose build app1-web && docker compose up -d app1-web   # só frontend
docker compose build app1 && docker compose up -d app1           # só API
```

Documentação: [apps/app1/README.md](apps/app1/README.md)

---

## AssistFin (App 2)

**URL:** https://assistfin.com.br

| Container | Função |
|-----------|--------|
| `hosting-app2` | FastAPI + agente Groq |
| `hosting-app2-db` | PostgreSQL 16 |

Finanças pessoais multiusuário: contas, cartões, faturas, movimentos, orçamentos, importação OFX/CSV/PDF, assistente com wizards e confirmação de escritas.

```bash
docker compose build app2 && docker compose up -d app2
docker compose exec -T app2 python -m pytest -q
```

Documentação: [apps/app2/README.md](apps/app2/README.md) · [AGENTS.md](apps/app2/AGENTS.md)

---

## Documentação por app

| App | README | Outros |
|-----|--------|--------|
| Tri Doçuras | [apps/app1/README.md](apps/app1/README.md) | [Frontend](apps/app1/frontend/README.md) · [API](apps/app1/api/README.md) |
| AssistFin | [apps/app2/README.md](apps/app2/README.md) | [ARCHITECTURE](apps/app2/docs/ARCHITECTURE.md) · [OPERATIONS](apps/app2/docs/OPERATIONS.md) · [CHANGELOG](apps/app2/docs/CHANGELOG.md) |

Design system Tri Doçuras: `/root/.cursor/docs/tri-docuras/design-system-tri-docuras.pdf`
