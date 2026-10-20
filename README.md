# Tri Doçuras — repositório da VPS

Repositório da loja **Tri Doçuras** (app1: Flutter web + API Dart Frog +
PostgreSQL, com painel da loja em `/admin`). Atualizado em 20/10/2026.

- **Produção:** https://tridocuras.com.br
- **Escopo do plano atual:** [`PLANO.md`](PLANO.md) (estado na seção 5)
- **Operação:** [`docs/OPERACAO.md`](docs/OPERACAO.md) (backup, restore, rollback, credenciais)
- **Monitoramento:** [`docs/MONITORAMENTO.md`](docs/MONITORAMENTO.md)
- **Documentação do app:** [`apps/app1/README.md`](apps/app1/README.md)

O AssistFin (finanças pessoais) roda em `/opt/assistfin`, com o Caddy desse
projeto como proxy. A pasta `apps/app2` deste repositório é uma cópia antiga
do AssistFin e está fora do escopo deste repositório (ver `PLANO.md`).

## Arquitetura

```
Internet :80/:443
    └── Caddy do AssistFin (/opt/assistfin/Caddyfile)
            └── tridocuras.com.br
                  ├── /        → app-tridocuras-web  (Flutter web + Nginx interno, CSP)
                  ├── /api/*   → app-tridocuras      (Dart Frog :8080)
                  └── /admin   → app-tridocuras      (painel da loja)

app-tridocuras ── app-tridocuras-db   (PostgreSQL 16, rede interna)
backup-tridocuras                      (pg_dump + tar dos uploads, 03:30)
```

## Compose ativo

O único compose em uso é `docker-compose.tridocuras.yml`, sempre a partir de
`/opt/tridocuras`:

```bash
cd /opt/tridocuras
docker compose -f docker-compose.tridocuras.yml ps
docker compose -f docker-compose.tridocuras.yml build app-tridocuras && \
  docker compose -f docker-compose.tridocuras.yml up -d app-tridocuras
```

| Serviço | Container | Função |
|---------|-----------|--------|
| `app-tridocuras-web` | `app-tridocuras-web` | Front Flutter web |
| `app-tridocuras` | `app-tridocuras` | API e painel |
| `app-tridocuras-db` | `app-tridocuras-db` | PostgreSQL 16 |
| `backup-tridocuras` | `backup-tridocuras` | Backup diário |

O `docker-compose.yml` da raiz é **antigo** (stack `hosting-*`, já desligada)
e não deve ser usado. Não rode `docker compose down -v`.

## Segredos

Credenciais ficam em `/opt/tridocuras/.env`, que não é versionado. Para
conferir as variáveis sem mostrar os valores:

```bash
sed 's/=.*/=<set>/' .env
```

O modelo sem valores está em [`.env.example`](.env.example).

## Estrutura

```
/opt/tridocuras/
├── docker-compose.tridocuras.yml   # compose ativo
├── .env                            # segredos (não versionar)
├── apps/
│   ├── app1/                       # Tri Doçuras: api/, frontend/, README.md
│   └── app2/                       # cópia antiga do AssistFin (fora do escopo)
├── scripts/                        # backup-tridocuras.sh e utilitários
├── docs/                           # OPERACAO.md e MONITORAMENTO.md
├── backups/                        # backups locais (ignorados pelo git)
├── nginx/ (antigo)                 # remover, ver PLANO.md, seção 4.4
├── PLANO.md, FASE0.md, CONTAS.md   # planos e registro de execução
└── .github/workflows/              # CI do app1
```

## Testes e CI

Os workflows `app1-tests.yml` (API) e `app1-frontend-tests.yml` (front) rodam
em push na `main` e em pull requests que mexem no app1. Detalhes e comandos
locais estão em [`apps/app1/README.md`](apps/app1/README.md#testes).

## Domínio

`APP1_DOMAIN` no `.env` (`tridocuras.com.br`). O webhook do Mercado Pago aponta
para `https://tridocuras.com.br/api/webhooks/mercadopago`.
