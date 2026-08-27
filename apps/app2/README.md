# App 2 — Placeholder

Segunda aplicação com stack isolada (container + PostgreSQL + volume próprio).

Domínio: `APP2_DOMAIN` em `/opt/hosting/.env` (padrão: `app2.example.com`).

```bash
cd /opt/hosting
docker compose up -d --build app2
```

Substituir o conteúdo de `apps/app2/` quando a segunda app for desenvolvida.
