---
name: tri-docuras-project
description: Tri Doçuras Flutter app conventions, design system, Docker deploy, and API integration. Use when editing tri_docuras, Tri Doçuras, brownies catalog, or files under apps/app1/frontend.
paths: lib/**,web/**,pubspec.yaml,android/**,ios/**
---

# Tri Doçuras — projeto Flutter

## Stack

- App: `/opt/hosting/apps/app1/frontend` (`tri_docuras` v1.0.0+1)
- API: Dart Frog em `/opt/hosting/apps/app1/api`
- Produção: https://tridocuras.com.br
- Painel loja: https://tridocuras.com.br/admin (`APP1_ADMIN_PASSWORD` em `/opt/hosting/.env`)
- Web deploy: `docker compose build app1 app1-web && docker compose up -d app1 app1-web` em `/opt/hosting`
- Design system PDF: `/root/.cursor/docs/tri-docuras/design-system-tri-docuras.pdf`

## API (endpoints usados pelo app)

| Método | Rota | Uso |
|--------|------|-----|
| GET | `/api/products` | Catálogo |
| POST | `/api/orders` | Checkout → criar pedido + Pix |
| GET | `/api/orders/{id}` | Polling pagamento Pix |
| POST | `/api/orders/{id}/pix` | Regenerar Pix expirado |
| GET | `/api/orders/{id}/tracking` | Timeline de rastreamento |

Admin (fora do Flutter): `POST /api/admin/session`, pedidos (`GET/POST /api/admin/orders*`), produtos (`GET/POST /api/admin/products`, `PUT /api/admin/products/{id}`). Painel: https://tridocuras.com.br/admin

## Integração Pix (Mercado Pago)

- **Gerar Pix** → `POST /api/orders` (grava pedido + retorna `pix.copy_code`)
- Tela 5 renderiza QR com `qr_flutter` a partir do `copy_code`
- Polling `GET /api/orders/{id}` até `status = paid`; webhook MP na API
- `mp_mode: test` na resposta → banner no app (Pix sandbox não paga em banco real)
- Credenciais: `APP1_MP_ACCESS_TOKEN`, `APP1_MP_PUBLIC_KEY`, `APP1_MP_USE_TEST` no `.env`
- Webhook produção: `https://tridocuras.com.br/api/webhooks/mercadopago` (evento **pagamentos**)

## Painel da loja

- URL: https://tridocuras.com.br/admin
- Senha: `APP1_ADMIN_PASSWORD` no `/opt/hosting/.env` (reiniciar `app1` após alterar)
- **Pedidos:** status `paid` → `preparing` → `ready` → `completed`
- **Produtos:** CRUD em `/api/admin/products` — nome, preço, categoria, destaque, visível (`available`)
- Código API: `admin_products.dart`, `admin_orders.dart`, `admin_panel_html.dart`

## Rastreamento (cliente)

- `order_tracking_screen.dart` — timeline + polling 15 s
- `OrderLookupScreen` na aba **Pedidos** (`home_screen.dart`)
- Botão na `confirmation_screen.dart`
- Modelo: `lib/models/order_tracking.dart`

## Favoritos e Perfil

- `lib/favorites/` — `FavoritesController` + `FavoritesScope`; persistência `shared_preferences`
- `favorites_screen.dart` — aba Favoritos (bottom nav índice 2)
- `profile_screen.dart` — aba Perfil (índice 3) + `StoreMenuSheet` (menu ☰ no catálogo)
- Coração em `product_screen.dart` — toggle via `FavoritesScope`
- WhatsApp da loja: `AppConfig.storeWhatsApp` em `config.dart` (não é variável de ambiente)
- Deps: `shared_preferences`, `url_launcher`

## Design system (v1)

### Paleta (`lib/theme/app_colors.dart`)

Dark `#412414`, Brown `#6A3A23`, Tan `#A4653C`, Cream `#FDEFE2`, Pink `#E6A6A4`, Pink Deep `#D67F7C`, Card `#FFFBF6`, Peach `#F7E3D0`, Sky `#99D2F3`, Disabled `#E6D9CC`, Success `#7C9473`, Warning `#C98A3C`.

### Componentes (`lib/widgets/`)

`TdButton`, `TdChip`, `TdSearchField`, `TdTextField`, `TdPhotoFrame`, `TdIconButton`, `TdQuantityStepper` (modo `compact` no carrinho).

### Carrinho (`lib/cart/`)

- `CartController` — memória; `deliveryFeeAmount = 6.0` para entrega; `removeAt`, `updateQuantity`
- `CartScope`, `DeliveryMode` (pickup/delivery)
- `CartAddedResult` + `CartAddedBanner` — balão 5 s no catálogo, link **Ver carrinho**

### Checkout (`lib/checkout/`)

- `CheckoutValidators` (nome/WhatsApp), `DeliveryAddressValidators` (rua, número, bairro, referência)
- Entrega só Nazaré da Mata - PE (CEP 55.800-000)
- `order_payload.dart` — monta body do `POST /api/orders`
- PII só em memória (`CheckoutDraft`); token MP só no backend

### Telas

| # | Arquivo | Notas |
|---|---------|-------|
| 1 | `home_screen.dart` | Catálogo; bottom nav: Início, Pedidos, Favoritos, Perfil |
| 2 | `product_screen.dart` | Favorito ♥ + Adicionar → pop com `CartAddedResult` |
| 3 | `cart_screen.dart` | Remover item, entrega R$ 6,00 |
| 4 | `checkout_screen.dart` | Nome, WhatsApp, endereço; `createOrder` |
| 5 | `pix_screen.dart` | QR + copia-e-cola, polling, confirmação automática |
| 6 | `confirmation_screen.dart` | Resumo + link rastreamento |
| — | `order_tracking_screen.dart` | Timeline + `OrderLookupScreen` |
| — | `favorites_screen.dart` | Lista favoritos (local) |
| — | `profile_screen.dart` | Info loja + `StoreMenuSheet` |

## Layout web

- Nav inferior no `body` (Column), não `bottomNavigationBar`
- `AppTheme.maxContentWidth` = 430px
- Hard refresh após deploy (`Ctrl+Shift+R`)

## API no cliente

- Web: `apiBaseUrl` = `/api` (`lib/config.dart`)
- Mobile: `https://tridocuras.com.br/api`
- `storeWhatsApp` / `appVersion` em `config.dart`
- Modelos: `created_order.dart`, `order_tracking.dart`

## Deploy e verificação

```bash
cd /opt/hosting && docker compose up -d --build app1 app1-web
curl -s https://tridocuras.com.br/api/health
```

## Testes

```bash
cd /opt/hosting/apps/app1/frontend && flutter test
```

## Pendente

Notificação WhatsApp; fotos dos produtos no catálogo.
