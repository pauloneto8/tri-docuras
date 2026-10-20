#!/bin/sh
# Backup diário da loja Tri Doçuras: dump do banco e tar dos uploads.
# Retenção: 14 diários + 8 semanais (cópia do domingo).
# Roda dentro do container backup-tridocuras (ver docker-compose.tridocuras.yml).
# Variáveis: DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME; diretórios fixos.
set -eu

DEST=/backups
UPLOADS=/data/uploads
STAMP=$(date +%F)
DIARIO="$DEST/diario"
SEMANAL="$DEST/semanal"
mkdir -p "$DIARIO" "$SEMANAL"

PGPASSWORD="$DB_PASSWORD" pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" \
  -d "$DB_NAME" -Fc > "$DIARIO/db-$STAMP.dump.tmp"
mv "$DIARIO/db-$STAMP.dump.tmp" "$DIARIO/db-$STAMP.dump"

tar czf "$DIARIO/uploads-$STAMP.tgz.tmp" -C "$UPLOADS" .
mv "$DIARIO/uploads-$STAMP.tgz.tmp" "$DIARIO/uploads-$STAMP.tgz"

if [ "$(date +%u)" = "7" ]; then
  cp "$DIARIO/db-$STAMP.dump" "$SEMANAL/db-$STAMP.dump"
  cp "$DIARIO/uploads-$STAMP.tgz" "$SEMANAL/uploads-$STAMP.tgz"
fi

# Mantém os 14 backups diários e os 8 semanais mais recentes.
ls -1 "$DIARIO"/db-*.dump | sort -r | tail -n +15 | xargs -r rm -f
ls -1 "$DIARIO"/uploads-*.tgz | sort -r | tail -n +15 | xargs -r rm -f
ls -1 "$SEMANAL"/db-*.dump | sort -r | tail -n +9 | xargs -r rm -f
ls -1 "$SEMANAL"/uploads-*.tgz | sort -r | tail -n +9 | xargs -r rm -f

echo "$(date -Is) backup ok ($STAMP)"
