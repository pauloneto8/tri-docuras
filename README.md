# Hosting — VPS Tri Doçuras

Infraestrutura Docker para hospedar duas aplicações isoladas, com Nginx como proxy reverso por domínio.

## Arquitetura

```
Internet :80/:443
    └── nginx (hosting-nginx)
            ├── APP1_DOMAIN → app1-web (Flutter) + /api → app1 (Dart Frog)
            └── APP2_DOMAIN → app2 (placeholder)
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
│   └── app2/               # segunda app (placeholder)
├── certs/                  # Let's Encrypt
├── scripts/
│   ├── reload-nginx.sh
│   └── issue-certs.sh
└── README.md
```

## Domínios (`.env`)

| Variável | Valor atual | Uso |
|----------|-------------|-----|
| `APP1_DOMAIN` | `tridocuras.example.com` | Tri Doçuras |
| `APP2_DOMAIN` | `app2.example.com` | App 2 |

Configure o DNS do domínio (`APP1_DOMAIN`) para apontar ao servidor antes de usar HTTPS.

## Comandos úteis

```bash
cd /opt/hosting

# Status
docker compose ps

# Subir tudo
docker compose up -d

# Rebuild Tri Doçuras
docker compose up -d --build app1 app1-web

# Logs
docker compose logs -f app1 app1-web nginx

# Recarregar Nginx após mudar domínio no .env
./scripts/reload-nginx.sh
```

## HTTPS (quando o DNS existir)

1. Edite `APP1_DOMAIN` e `CERTBOT_EMAIL` no `.env`
2. Aponte o registro **A** do domínio ao IP público do servidor (no provedor/DNS)
3. `./scripts/reload-nginx.sh`
4. `./scripts/issue-certs.sh`

## Firewall (UFW)

Expor apenas as portas necessárias para o app web (`80`, `443`) e SSH conforme a política do provedor.

## Tri Doçuras (App 1)

Frontend Flutter web alinhado ao Design System v1. Telas implementadas: **catálogo**, **produto**, **carrinho** e **checkout** (Pix em placeholder). Carrinho em memória via `CartController`; API expõe catálogo (`GET /api/products`).

Rebuild após mudanças no UI:

```bash
docker compose build app1-web && docker compose up -d app1-web
```

## Documentação por app

- [Tri Doçuras (App 1)](apps/app1/README.md)
- [Flutter — frontend](apps/app1/frontend/README.md)
- [API Dart Frog](apps/app1/api/README.md)
- [Design system — índice](/root/.cursor/docs/tri-docuras/README.md)
- Design system (PDF): `/root/.cursor/docs/tri-docuras/design-system-tri-docuras.pdf`
- Renders PNG: `/root/.cursor/docs/tri-docuras/render/`
