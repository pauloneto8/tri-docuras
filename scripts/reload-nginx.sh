#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

set -a
# shellcheck disable=SC1091
source .env
set +a

echo "Recriando Nginx para aplicar novos domínios..."
docker compose up -d --force-recreate nginx

echo "Nginx recarregado com APP1_DOMAIN=$APP1_DOMAIN e APP2_DOMAIN=$APP2_DOMAIN"
