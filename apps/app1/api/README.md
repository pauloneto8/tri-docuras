# Tri Doçuras — API (Dart Frog)

API REST em Dart para catálogo, pedidos e pagamento Pix via Mercado Pago.

O frontend Flutter consome estes endpoints no checkout e na tela de pagamento.

## Endpoints

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/api/health` | Status + ping PostgreSQL |
| GET | `/api/products` | Lista de produtos ativos |
| GET | `/api/config` | Config pública da loja (nome, WhatsApp) |
| POST | `/api/orders` | Cria pedido (`pending_payment`) + gera Pix |
| GET | `/api/orders/{id}` | Consulta status (`pending_payment` / `paid`) |
| POST | `/api/orders/{id}/pix` | Regenera cobrança Pix (se expirada) |
| POST | `/api/webhooks/mercadopago` | Webhook de confirmação de pagamento |
| GET | `/api/orders/{id}/tracking` | Timeline de rastreamento para o cliente |
| POST | `/api/admin/session` | Login do painel (senha → token) |
| GET | `/api/admin/orders` | Lista pedidos (`search`, `from`, `to` opcionais) |
| POST | `/api/admin/orders/{id}/status` | Atualiza status do pedido (inclui `cancelled`) |
| GET | `/api/admin/products` | Lista produtos (inclui ocultos) + categorias |
| POST | `/api/admin/products` | Cria produto |
| PUT | `/api/admin/products/{id}` | Atualiza produto |
| POST | `/api/admin/products/{id}/image` | Upload da foto do produto |
| GET | `/api/admin/categories` | Lista categorias |
| POST | `/api/admin/categories` | Cria categoria |
| PUT | `/api/admin/categories/{id}` | Atualiza categoria |
| DELETE | `/api/admin/categories/{id}` | Remove categoria (se não houver produtos) |
| GET | `/api/admin/finance/report` | Relatório de faturamento (`from`, `to`) |
| GET | `/api/uploads/products/{filename}` | Foto do produto |
| GET | `/admin` | Painel web (pedidos + produtos + financeiro) |

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

### Exemplo — rastreamento (cliente)

```bash
curl -s https://tridocuras.com.br/api/orders/TD-0001/tracking
```

```json
{
  "order": {
    "id": "TD-0001",
    "status": "preparing",
    "status_label": "Em preparo",
    "delivery_mode": "pickup",
    "delivery_label": "Retirada",
    "total": 24.0,
    "is_paid": true,
    "is_completed": false
  },
  "timeline": [
    {"key": "received", "label": "Pedido recebido", "done": true, "current": false},
    {"key": "paid", "label": "Pagamento confirmado", "done": true, "current": false},
    {"key": "preparing", "label": "Em preparo", "done": true, "current": true}
  ]
}
```

### Exemplo — login do painel

```bash
curl -s -X POST https://tridocuras.com.br/api/admin/session \
  -H 'Content-Type: application/json' \
  -d '{"password":"SUA_SENHA"}'
```

Resposta: `{ "token": "..." }`. Use em `Authorization: Bearer <token>` nas rotas `/api/admin/*`.

### Exemplo — listar pedidos (admin)

```bash
curl -s "https://tridocuras.com.br/api/admin/orders?status=active" \
  -H "Authorization: Bearer SEU_TOKEN"
```

### Exemplo — atualizar status (admin)

```bash
curl -s -X POST https://tridocuras.com.br/api/admin/orders/TD-0001/status \
  -H "Authorization: Bearer SEU_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"status":"preparing"}'
```

### Exemplo — listar produtos (admin)

```bash
curl -s https://tridocuras.com.br/api/admin/products \
  -H "Authorization: Bearer SEU_TOKEN"
```

Resposta inclui todos os produtos (`available: true` e `false`) e `categories: ["brownies", "combos"]`.

### Exemplo — criar produto (admin)

```bash
curl -s -X POST https://tridocuras.com.br/api/admin/products \
  -H "Authorization: Bearer SEU_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Brownie Especial",
    "description": "Edição limitada",
    "price": 18.00,
    "category": "brownies",
    "featured": false,
    "available": true
  }'
```

### Exemplo — editar produto (admin)

```bash
curl -s -X PUT https://tridocuras.com.br/api/admin/products/4 \
  -H "Authorization: Bearer SEU_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Brownie Tradicional",
    "description": "Brownie amanteigado clássico.",
    "price": 13.00,
    "category": "brownies",
    "featured": true,
    "available": true
  }'
```

Para ocultar do catálogo público, envie `"available": false` (soft-delete; pedidos antigos mantêm snapshot em `order_items`).

## Ciclo de vida do status

| Status | Descrição |
|--------|-----------|
| `pending_payment` | Aguardando Pix |
| `paid` | Pagamento confirmado (webhook MP) |
| `preparing` | Em preparo (painel admin) |
| `ready` | Pronto para retirada/entrega |
| `completed` | Retirado ou entregue |
| `cancelled` | Cancelado no painel (fora do faturamento) |

## Tabelas

| Tabela | Uso |
|--------|-----|
| `products` | Catálogo |
| `product_categories` | Categorias editáveis (`slug`, `label`, `sort_order`, `active`) |
| `orders` | Pedido (cliente, entrega, totais, `public_id` tipo `TD-0001`, campos MP/Pix) |
| `order_items` | Itens com snapshot de nome e preço unitário |

Colunas Mercado Pago em `orders`: `mp_payment_id`, `pix_copy_code`, `pix_qr_base64`, `pix_expires_at`, `paid_at`.

## Estrutura

```
api/
├── lib/
│   ├── db.dart                    # Postgres, schema, seed
│   ├── orders.dart                # Validação, criação, Pix, webhook sync
│   ├── order_tracking.dart        # Timeline para o cliente
│   ├── admin_orders.dart          # Listagem, filtros e status (painel)
│   ├── admin_products.dart        # CRUD de produtos (painel)
│   ├── admin_categories.dart      # CRUD de categorias (painel)
│   ├── finance.dart               # Relatório de faturamento (painel)
│   ├── admin_auth.dart            # Autenticação do painel
│   ├── admin_panel_html.dart      # UI HTML do /admin
│   ├── mercado_pago_client.dart   # Cliente API MP v1 payments
│   └── mercado_pago_config.dart   # Credenciais e URL do webhook
├── routes/
│   ├── _middleware.dart           # CORS + init DB
│   ├── admin/
│   │   └── index.dart             # GET /admin (HTML)
│   └── api/
│       ├── health.dart
│       ├── products.dart
│       ├── admin/
│       │   ├── session.dart         # POST login
│       │   ├── orders/              # GET lista, POST status
│       │   ├── products/            # GET/POST lista e criar; PUT por id
│       │   ├── categories/          # GET/POST; PUT/DELETE por id
│       │   └── finance/             # GET relatório de faturamento
│       ├── orders/
│       │   ├── index.dart           # POST create
│       │   └── [id]/
│       │       ├── index.dart       # GET status
│       │       ├── pix.dart         # POST regenerar Pix
│       │       └── tracking.dart    # GET timeline cliente
│       └── webhooks/
│           └── mercadopago.dart
├── test/
│   ├── mercado_pago_client_test.dart
│   ├── admin_orders_test.dart
│   ├── admin_products_test.dart
│   └── order_tracking_test.dart
├── bin/
│   ├── wait_for_db.dart
│   └── seed.dart
├── Dockerfile
└── entrypoint.sh
```

## Banco de dados

Tabelas criadas em `ensureSchema` no startup (idempotente).

Credenciais via variáveis de ambiente (`docker-compose.tridocuras.yml` → `APP1_DB_*` em `/opt/tridocuras/.env`).

O `entrypoint.sh` aguarda o Postgres, aplica schema/seed e inicia o servidor.

## Painel admin (`/admin`)

Interface HTML com três seções: **Pedidos**, **Produtos** e **Financeiro** (`admin_panel_html.dart`).

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/admin` | Interface web (HTML) |
| POST | `/api/admin/session` | `{ "password": "..." }` → `{ "token": "..." }` |
| GET | `/api/admin/orders?status=active&search=Maria&from=2026-09-01&to=2026-09-30` | Lista pedidos (`Authorization: Bearer <token>`) |
| POST | `/api/admin/orders/{id}/status` | `{ "status": "preparing" }` etc. (inclui `cancelled`) |
| GET | `/api/admin/products` | Lista produtos (inclui ocultos) + categorias |
| POST | `/api/admin/products` | Cria produto |
| PUT | `/api/admin/products/{id}` | Atualiza produto (inclui `available`) |
| GET/POST | `/api/admin/categories` | Lista / cria categorias |
| PUT/DELETE | `/api/admin/categories/{id}` | Edita / remove categoria |
| GET | `/api/admin/finance/report?from=&to=` | Faturamento do período |

**Pedidos** — filtros `status`: `active` (fila), `paid`, `preparing`, `ready`, `pending_payment`, `completed`, `cancelled`. Busca por ID/cliente (`search`) e período por data de criação (`from`/`to`, `AAAA-MM-DD`).

**Produtos** — categorias editáveis (tabela `product_categories`; padrão `brownies`, `combos`). Campo `available: false` oculta do `GET /api/products` sem apagar o registro. Excluir uma categoria exige mover os produtos antes.

**Financeiro** — relatório de leitura derivado dos pedidos pagos (`paid`, `preparing`, `ready`, `completed`), agrupado por dia no fuso `America/Recife`: faturamento, nº de pedidos, ticket médio, taxas de entrega, série diária e vendas por produto. Cancelados e aguardando Pix ficam fora.

Fluxo de status após pagamento: `paid` → `preparing` → `ready` → `completed`; `cancelled` encerra o pedido (irreversível) e o exclui do faturamento.

**Configuração:**

1. Defina `APP1_ADMIN_PASSWORD` no `/opt/tridocuras/.env` (não commitar).
2. `docker compose -f docker-compose.tridocuras.yml up -d app-tridocuras` após alterar a senha.
3. Nginx deve rotear `/admin` para `app1:8080` (já configurado em `nginx/ssl/app1.conf`).

O login (`POST /api/admin/session`) retorna um token Bearer válido enquanto a senha não mudar.

## Mercado Pago (Pix)

Variáveis no `/opt/tridocuras/.env` (repassadas ao container `app1`):

| Variável no `.env` | Variável no container | Uso |
|--------------------|----------------------|-----|
| `APP1_MP_ACCESS_TOKEN` | `MP_ACCESS_TOKEN` | Access Token de produção |
| `APP1_MP_PUBLIC_KEY` | `MP_PUBLIC_KEY` | Public Key de produção |
| `APP1_MP_TEST_ACCESS_TOKEN` | `MP_TEST_ACCESS_TOKEN` | Access Token de teste |
| `APP1_MP_TEST_PUBLIC_KEY` | `MP_TEST_PUBLIC_KEY` | Public Key de teste |
| `APP1_MP_USE_TEST` | `MP_USE_TEST` | `true` = sandbox; `false` = produção |
| `APP1_DOMAIN` | `APP1_DOMAIN` | Domínio público (monta URL do webhook) |
| `APP1_ADMIN_PASSWORD` | `APP1_ADMIN_PASSWORD` | Senha do painel `/admin` |

Webhook no painel MP: `https://tridocuras.com.br/api/webhooks/mercadopago`

O Access Token é enviado apenas no header `Authorization: Bearer ...` (nunca em query string).

**Modo teste:** Pix gerado com credenciais `TEST-...` **não** é aceito em apps bancários reais. Use `APP1_MP_USE_TEST=false` para pagamentos de verdade.

A resposta Pix inclui `mp_mode`: `test` ou `production` (o app exibe aviso em modo teste).

## Desenvolvimento local

```bash
cd /opt/tridocuras/apps/app1/api
dart pub get
dart pub global activate dart_frog_cli
dart_frog dev
# http://localhost:8080/api/health
```

Requer PostgreSQL acessível ou variáveis `DB_*` / `DATABASE_URL`.

## Deploy

```bash
cd /opt/tridocuras
docker compose -f docker-compose.tridocuras.yml build app-tridocuras
docker compose -f docker-compose.tridocuras.yml up -d app-tridocuras
```

Container: `app-tridocuras` — porta interna 8080, rede `proxy` + `app1_internal`.

Após mudança no frontend, rebuild também `app1-web` e use hard refresh no navegador.

## Monitoramento

```bash
curl -s https://tridocuras.com.br/api/health
docker compose -f docker-compose.tridocuras.yml logs --tail=50 app-tridocuras
docker compose -f docker-compose.tridocuras.yml exec app-tridocuras-db psql -U "$APP1_DB_USER" -d "$APP1_DB_NAME" -c "SELECT public_id, status, total FROM orders ORDER BY id DESC LIMIT 5;"
```

## CORS

Restrito em produção: apenas `https://<APP1_DOMAIN>` (e `www.`) e origens de dev local (`localhost`, `127.0.0.1`). Sem header `Origin` (curl, apps nativos) não há CORS aplicado.

## Roadmap (API)

| Endpoint / recurso | Descrição |
|--------------------|-----------|
| Fotos de produtos | Implementado — upload no painel + exibição no catálogo |
| Notificação WhatsApp | Implementado — loja e cliente ao confirmar pagamento |
| Templates WhatsApp adicionais | Novos templates além de `order_paid` |
| PWA | Web instalável com notificação push |
| App mobile nativo | Build Android/iOS com assinatura de release |
