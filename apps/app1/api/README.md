# Tri Doçuras — API (Dart Frog)

API REST em Dart para catálogo, pedidos e pagamento Pix via Mercado Pago.

O frontend Flutter consome estes endpoints no checkout e na tela de pagamento.

## Endpoints

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/api/health` | Status + ping PostgreSQL |
| GET | `/api/products` | Lista de produtos ativos |
| POST | `/api/orders` | Cria pedido (`pending_payment`) + gera Pix |
| GET | `/api/orders/{id}` | Consulta status (`pending_payment` / `paid`) |
| POST | `/api/orders/{id}/pix` | Regenera cobrança Pix (se expirada) |
| POST | `/api/webhooks/mercadopago` | Webhook de confirmação de pagamento |

### Exemplo — health

```bash
curl https://tridocuras.com.br/api/health
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

### Exemplo — create order

```bash
curl -s -X POST https://tridocuras.com.br/api/orders \
  -H 'Content-Type: application/json' \
  -d '{
    "customer_name": "Maria Silva",
    "whatsapp": "81991234567",
    "delivery_mode": "pickup",
    "items": [{"product_id": 4, "quantity": 2, "lactose_free": false}]
  }'
```

```json
{
  "order": {
    "id": "TD-0001",
    "status": "pending_payment",
    "subtotal": 24.0,
    "delivery_fee": 0.0,
    "total": 24.0,
    "paid_at": null,
    "pix_expires_at": "2026-09-07T03:15:00.000Z"
  },
  "pix": {
    "payment_id": 1351501105,
    "copy_code": "00020126...",
    "qr_code_base64": "...",
    "expires_at": "2026-09-07T03:15:00.000Z",
    "status": "pending",
    "mp_mode": "production"
  }
}
```

Sem token Mercado Pago configurado, o pedido é criado mas a resposta inclui `pix_error`.

O servidor recalcula preços a partir do catálogo (inclui +R$ 3 sem lactose). Taxa de entrega: R$ 6,00 quando `delivery_mode` = `delivery`.

### Exemplo — consultar status

```bash
curl -s https://tridocuras.com.br/api/orders/TD-0001
```

```json
{
  "order": {
    "id": "TD-0001",
    "status": "paid",
    "subtotal": 24.0,
    "delivery_fee": 0.0,
    "total": 24.0,
    "paid_at": "2026-09-07T03:10:00.000Z",
    "pix_expires_at": "2026-09-07T03:15:00.000Z"
  }
}
```

### Exemplo — regenerar Pix

```bash
curl -s -X POST https://tridocuras.com.br/api/orders/TD-0001/pix
```

## Tabelas

| Tabela | Uso |
|--------|-----|
| `products` | Catálogo |
| `orders` | Pedido (cliente, entrega, totais, `public_id` tipo `TD-0001`, campos MP/Pix) |
| `order_items` | Itens com snapshot de nome e preço unitário |

Colunas Mercado Pago em `orders`: `mp_payment_id`, `pix_copy_code`, `pix_qr_base64`, `pix_expires_at`, `paid_at`.

## Estrutura

```
api/
├── lib/
│   ├── db.dart                    # Postgres, schema, seed
│   ├── orders.dart                # Validação, criação, Pix, webhook sync
│   ├── mercado_pago_client.dart   # Cliente API MP v1 payments
│   └── mercado_pago_config.dart   # Credenciais e URL do webhook
├── routes/
│   ├── _middleware.dart           # CORS + init DB
│   └── api/
│       ├── health.dart
│       ├── products.dart
│       ├── orders/
│       │   ├── index.dart         # POST create
│       │   └── [id]/
│       │       ├── index.dart     # GET status
│       │       └── pix.dart       # POST regenerar Pix
│       └── webhooks/
│           └── mercadopago.dart
├── bin/
│   ├── wait_for_db.dart
│   └── seed.dart
├── Dockerfile
└── entrypoint.sh
```

## Banco de dados

Tabelas criadas em `ensureSchema` no startup (idempotente).

Credenciais via variáveis de ambiente (`docker-compose.yml` → `APP1_DB_*` em `/opt/hosting/.env`).

O `entrypoint.sh` aguarda o Postgres, aplica schema/seed e inicia o servidor.

## Mercado Pago (Pix)

Variáveis no `/opt/hosting/.env` (repassadas ao container `app1`):

| Variável no `.env` | Variável no container | Uso |
|--------------------|----------------------|-----|
| `APP1_MP_ACCESS_TOKEN` | `MP_ACCESS_TOKEN` | Access Token de produção |
| `APP1_MP_TEST_ACCESS_TOKEN` | `MP_TEST_ACCESS_TOKEN` | Access Token de teste |
| `APP1_MP_TEST_PUBLIC_KEY` | `MP_TEST_PUBLIC_KEY` | Public Key de teste |
| `APP1_MP_USE_TEST` | `MP_USE_TEST` | `true` = sandbox; `false` = produção |
| `APP1_DOMAIN` | `APP1_DOMAIN` | Domínio público (monta URL do webhook) |

Webhook no painel MP: `https://tridocuras.com.br/api/webhooks/mercadopago`

O Access Token é enviado apenas no header `Authorization: Bearer ...` (nunca em query string).

**Modo teste:** Pix gerado com credenciais `TEST-...` **não** é aceito em apps bancários reais. Use `APP1_MP_USE_TEST=false` para pagamentos de verdade.

A resposta Pix inclui `mp_mode`: `test` ou `production` (o app exibe aviso em modo teste).

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

Container: `hosting-app1` — porta interna 8080, rede `proxy` + `app1_internal`.

Após mudança no frontend, rebuild também `app1-web` e use hard refresh no navegador.

## Monitoramento

```bash
curl -s https://tridocuras.com.br/api/health
docker compose logs --tail=50 app1
docker compose exec app1-db psql -U "$APP1_DB_USER" -d "$APP1_DB_NAME" -c "SELECT public_id, status, total FROM orders ORDER BY id DESC LIMIT 5;"
```

## CORS

Liberado para desenvolvimento (`Access-Control-Allow-Origin: *` no middleware).

## Roadmap (API)

| Endpoint / recurso | Descrição |
|--------------------|-----------|
| `GET /api/orders/{id}/tracking` | Rastreamento de entrega (futuro) |
