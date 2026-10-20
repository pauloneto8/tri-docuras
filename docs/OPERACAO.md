# Operação da loja Tri Doçuras

Procedimentos de operação. Estado descrito em 20/10/2026.
Monitoramento e alertas: [`MONITORAMENTO.md`](MONITORAMENTO.md).

Regras gerais:

- Todo comando de container usa `docker compose -f docker-compose.tridocuras.yml`,
  a partir de `/opt/tridocuras`. **Nunca** use o `docker-compose.yml` da raiz (antigo).
- Nunca rode `docker compose down -v`.
- Não mostre segredos (`.env`) em chat, log ou commit. Para conferir variáveis:
  `sed 's/=.*/=<set>/' .env`.

## Backups

**O que é feito:** todo dia às 03:30 (Recife), o container `backup-tridocuras`
roda `scripts/backup-tridocuras.sh`:

- `diario/db-AAAA-MM-DD.dump`: dump do banco (formato custom do `pg_dump`).
- `diario/uploads-AAAA-MM-DD.tgz`: fotos dos produtos.
- Aos domingos, cópia também em `semanal/`.
- Retenção: 14 diários e 8 semanais. Os mais antigos são apagados automaticamente.

Local: `/opt/tridocuras/backups/tridocuras/` (no mesmo disco da VPS).

**Pendência:** ainda não há cópia fora da VPS. Se o disco da VPS falhar, os
backups se perdem junto. Ver `PLANO.md`, Fase 1.1.

**Conferir se rodou:**

```bash
ls -la /opt/tridocuras/backups/tridocuras/diario/
docker logs --tail 5 backup-tridocuras     # linha "backup ok (AAAA-MM-DD)"
```

**Rodar manualmente agora:**

```bash
docker exec backup-tridocuras sh /backup.sh
```

## Restore de teste (não toca na produção)

Testado em 20/10/2026 com o backup de 19/10: restaurou 7 produtos, 1 pedido e
1 item de pedido, e o tar dos uploads abriu sem erro.

Use um Postgres descartável, separado da loja:

```bash
B=/opt/tridocuras/backups/tridocuras/diario
DUMP=db-2026-10-19.dump          # ajuste a data

docker run -d --name restore-check -e POSTGRES_PASSWORD=x postgres:16-alpine
sleep 6
docker cp "$B/$DUMP" restore-check:/tmp/d.dump
docker exec restore-check sh -c 'createdb -U postgres t && pg_restore --no-owner -U postgres -d t /tmp/d.dump && psql -U postgres -d t -Atc "select count(*) from products; select count(*) from orders;"'
docker rm -f restore-check
```

Para conferir as fotos: `tar tzf "$B/uploads-2026-10-19.tgz"`.

## Restore real (perda de dados na produção)

Só faça isso com autorização do dono, porque sobrescreve o banco atual.

1. Pare a API para não receber pedidos durante o restore:
   `docker stop app-tridocuras`.
2. Faça um dump do estado atual antes de qualquer coisa, mesmo que esteja
   quebrado.
3. Restaure no banco da loja (`app-tridocuras-db`), com a API parada:

   ```bash
   docker cp "$B/$DUMP" app-tridocuras-db:/tmp/d.dump
   docker exec app-tridocuras-db sh -c 'pg_restore --clean --if-exists --no-owner -U "$POSTGRES_USER" -d "$POSTGRES_DB" /tmp/d.dump'
   ```

4. Para as fotos, restaure o volume `tridocuras_uploads` a partir do tar com o
   mesmo procedimento de `tar xzf` dentro de um container temporário que monta
   o volume.
5. Suba a API de novo: `docker start app-tridocuras`, e confira
   `curl -s https://tridocuras.com.br/api/health`.

## Rollback de deploy

Cada commit do app1 vai para o `main`. Para voltar uma versão:

```bash
cd /opt/tridocuras
git log --oneline -5                  # escolha o commit bom
git revert <commit-ruim>              # não use reset em main
docker compose -f docker-compose.tridocuras.yml build app-tridocuras
docker compose -f docker-compose.tridocuras.yml up -d app-tridocuras
```

Use o mesmo procedimento com `app-tridocuras-web` para o front.
Migrações de banco são idempotentes (`ADD COLUMN IF NOT EXISTS`), então um
rollback de código não remove colunas. Isso é intencional.

## Estorno de pedido pago

Pelo painel (`/admin`), cancelar um pedido pago pergunta se deve estornar o
valor ao cliente. Se o Mercado Pago recusar, o pedido **não** é cancelado e o
motivo aparece na tela. Para estornar pelo painel do Mercado Pago, cancele sem
estorno no painel da loja e faça o estorno manualmente no MP.

## Trocar credenciais

- **Mercado Pago:** trocar `APP1_MP_ACCESS_TOKEN`, `APP1_MP_PUBLIC_KEY` ou
  `APP1_MP_WEBHOOK_SECRET` no `.env` e recriar com
  `docker compose -f docker-compose.tridocuras.yml up -d app-tridocuras`
  (o `env_file` só é relido ao recriar).
- **Senha do painel:** `APP1_ADMIN_PASSWORD` no `.env`, seguido do mesmo `up -d`.
  Trocar a senha não invalida tokens já emitidos, que expiram sozinhos.
