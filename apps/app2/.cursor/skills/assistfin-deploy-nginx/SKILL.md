---
name: assistfin-deploy-nginx
description: >-
  Deploy e proxy Nginx do AssistFin em /opt/hosting: docker compose, templates,
  SSL, rate-limit, headers e reload. Use ao publicar app2, mudar domínio,
  configurar HTTPS, debugar 502/timeout no chat /agent/ ou alterar nginx em /opt/hosting.
---

# AssistFin — Deploy e Nginx

Documentação: [README.md](../../README.md), [docs/OPERATIONS.md](../../docs/OPERATIONS.md), [docs/SECURITY.md](../../docs/SECURITY.md).

## Arquitetura

```
Internet :80
  └── hosting-nginx (proxy)
        └── app2:8000 (AssistFin, rede proxy)
              ├── app2-db (rede app2_internal)
              └── ollama (só app2_internal — não exposto)
```

- Código: `/opt/hosting/apps/app2`
- Infra: `/opt/hosting` (compose, nginx, `.env`)
- Servidor atual: IP público, HTTP na porta 80 (HTTPS quando DNS + certs)

## Deploy do App2

```bash
cd /opt/hosting
docker compose build app2
docker compose up -d app2
docker compose exec -T app2 python -m pytest -q
```

Ordem recomendada após mudança de código:

1. `build app2` + `up -d app2`
2. Verificar health: `curl -s http://localhost/api/health` (via nginx) ou logs
3. Só então `reload-nginx.sh` se alterou domínio/template nginx

## Recarregar Nginx

```bash
cd /opt/hosting
./scripts/reload-nginx.sh
```

- Lê `.env` (`APP1_DOMAIN`, `APP2_DOMAIN`)
- Recria container `hosting-nginx` com templates atualizados
- Templates em `nginx/templates/*.conf.template` → processados pelo entrypoint oficial do image nginx

## Template App2 (`nginx/templates/app2.conf.template`)

| Location | Comportamento |
|----------|---------------|
| `/login`, `/register` | `limit_req zone=auth_limit` (5 req/min) |
| `/agent/` | proxy com timeout **120s** (LLM lento) |
| `/` | proxy padrão para FastAPI |

Headers de segurança espelham `app/main.py` (CSP, X-Frame-Options, etc.).

## Variáveis `.env` relevantes

| Variável | Uso |
|----------|-----|
| `APP2_DOMAIN` | `server_name` no nginx + `TRUSTED_HOSTS` no app2 |
| `APP2_SECRET_KEY` | sessão — obrigatória |
| `APP2_GROQ_API_KEY` | fallback LLM |
| `APP2_ROOT_EMAILS` | admin root |
| `APP2_ALLOW_REGISTRATION` | registro público |

**Nunca** commitar `.env`. Permissão recomendada: `600`.

## HTTPS (quando houver domínio)

```bash
# 1. DNS A record → IP do servidor
# 2. Ajustar APP2_DOMAIN no .env
./scripts/reload-nginx.sh
./scripts/issue-certs.sh   # gera nginx/ssl/app2.conf
```

Porta 443 pode estar despublicada até certificado válido existir.

## Troubleshooting

| Sintoma | Verificar |
|---------|-----------|
| 502 Bad Gateway | `docker compose ps app2` — container rodando? |
| Chat trava / timeout | timeout `/agent/` no nginx (120s); Groq/Ollama |
| Redirect loop login | `TRUSTED_HOSTS` inclui domínio real |
| 429 no login | rate-limit nginx `auth_limit` — esperar 1 min |
| Mudança não aparece | rebuild `app2`, não só reload nginx |

```bash
docker compose logs -f app2 nginx
docker compose exec nginx nginx -t
```

## Checklist de deploy seguro

- [ ] `APP2_SECRET_KEY` definida (não default)
- [ ] Ollama só em `app2_internal`
- [ ] App2 roda como `appuser` (Dockerfile)
- [ ] Testes passando no container
- [ ] Nginx com `server_tokens off` e `client_max_body_size 1m`

## Referência

Detalhes SSL e compose: [nginx-reference.md](nginx-reference.md)
