#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  echo "Arquivo .env não encontrado em $ROOT_DIR" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

if [[ -z "${CERTBOT_EMAIL:-}" || "$CERTBOT_EMAIL" == "admin@example.com" ]]; then
  echo "Defina CERTBOT_EMAIL no arquivo .env antes de emitir certificados." >&2
  exit 1
fi

if [[ -z "${APP1_DOMAIN:-}" || -z "${APP2_DOMAIN:-}" ]]; then
  echo "Defina APP1_DOMAIN e APP2_DOMAIN no arquivo .env." >&2
  exit 1
fi

echo "Emitindo certificados para $APP1_DOMAIN (e www) e $APP2_DOMAIN..."
docker compose --profile certbot run --rm certbot certonly \
  --webroot \
  -w /var/www/certbot \
  -d "$APP1_DOMAIN" \
  -d "www.$APP1_DOMAIN" \
  -d "$APP2_DOMAIN" \
  -d "www.$APP2_DOMAIN" \
  --email "$CERTBOT_EMAIL" \
  --agree-tos \
  --no-eff-email \
  --non-interactive

mkdir -p nginx/ssl

echo "Gerando configurações SSL do Nginx..."
envsubst '${APP1_DOMAIN}' < nginx/templates/ssl/app1.ssl.conf.template > nginx/ssl/app1.conf
envsubst '${APP2_DOMAIN}' < nginx/templates/ssl/app2.ssl.conf.template > nginx/ssl/app2.conf

echo "Desativando templates HTTP-only (substituídos pelos blocos SSL)..."
for f in app1.conf.template app2.conf.template; do
  if [[ -f "nginx/templates/$f" ]]; then
    mv "nginx/templates/$f" "nginx/templates/${f}.disabled"
  fi
done

echo "Recriando Nginx com HTTPS..."
docker compose up -d --force-recreate nginx
docker compose exec nginx nginx -t

echo "Certificados emitidos e HTTPS ativado."
