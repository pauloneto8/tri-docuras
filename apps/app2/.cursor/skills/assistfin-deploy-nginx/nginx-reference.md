# Referência Nginx / Docker — AssistFin

## Redes Docker (`docker-compose.yml`)

| Rede | Serviços |
|------|----------|
| `proxy` | nginx, app1, app1-web, app2 |
| `app2_internal` | app2, app2-db, ollama |

Ollama **não** está na rede `proxy` — inacessível da internet.

## Comandos úteis

```bash
cd /opt/hosting
docker compose ps
docker compose logs -f app2 --tail=100
docker compose exec -T app2-db psql -U app2 -d app2 -c '\dt'
docker compose restart app2
```

## Editar template nginx

1. Alterar `nginx/templates/app2.conf.template`
2. `./scripts/reload-nginx.sh`
3. `docker compose exec nginx nginx -t`

## App2 entrypoint

`apps/app2/entrypoint.sh` — roda migrações Alembic antes de uvicorn.

## Firewall

Expor apenas `80` (e `443` com TLS). SSH conforme política do VPS.
