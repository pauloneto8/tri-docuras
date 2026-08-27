# Tri Doçuras — API (Dart Frog)

API REST em Dart para catálogo de produtos e integração com o app Flutter.

## Endpoints

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/api/health` | Status + ping PostgreSQL |
| GET | `/api/products` | Lista de produtos ativos |

### Exemplo — health

```bash
curl -H "Host: tridocuras.example.com" http://143.95.165.99/api/health
```

```json
{"status":"ok","service":"Tri Doçuras API","database":"connected"}
```

### Exemplo — products

```json
{
  "products": [
    {
      "id": 4,
      "name": "Brownie Tradicional",
      "description": "...",
      "price": 12.0,
      "featured": true,
      "category": "brownies",
      "available": true
    }
  ]
}
```

Categorias: `brownies`, `combos`.

## Estrutura

```
api/
├── lib/db.dart              # Postgres, schema, seed
├── routes/
│   ├── _middleware.dart     # CORS + init DB
│   └── api/
│       ├── health.dart
│       └── products.dart
├── bin/
│   ├── wait_for_db.dart
│   └── seed.dart
├── Dockerfile
└── entrypoint.sh
```

## Banco de dados

Tabela `products`: `id`, `name`, `description`, `price`, `featured`, `category`, `available`.

Credenciais via variáveis de ambiente (ver `docker-compose.yml` e `.env` em `/opt/hosting`).

## Desenvolvimento local

```bash
cd /opt/hosting/apps/app1/api
dart pub get
dart pub global activate dart_frog_cli
dart_frog dev
# http://localhost:8080/api/health
```

Requer PostgreSQL acessível ou variáveis `DB_*` / `DATABASE_URL`.

## Deploy

```bash
cd /opt/hosting
docker compose build app1
docker compose up -d app1
```

O container aguarda o banco, roda seed e inicia `dart build/bin/server.dart` na porta 8080.

## CORS

Liberado para desenvolvimento (`Access-Control-Allow-Origin: *` no middleware).
