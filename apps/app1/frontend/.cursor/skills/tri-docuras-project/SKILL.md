---
name: tri-docuras-project
description: Tri Doçuras Flutter app conventions, design system, Docker deploy, and API integration. Use when editing tri_docuras, Tri Doçuras, brownies catalog, or files under apps/app1/frontend.
paths: lib/**,web/**,pubspec.yaml,android/**,ios/**
---

# Tri Doçuras — projeto Flutter

## Stack

- App: `/opt/hosting/apps/app1/frontend` (`tri_docuras`)
- API: Dart Frog em `/opt/hosting/apps/app1/api` — `GET /api/products`, `GET /api/health`
- Produção: https://tridocuras.com.br
- Web deploy: `docker compose build app1-web` em `/opt/hosting`
- Design system PDF: `/root/.cursor/docs/tri-docuras/design-system-tri-docuras.pdf`

## Design system (v1)

### Paleta (`lib/theme/app_colors.dart`)

Dark `#412414`, Brown `#6A3A23`, Tan `#A4653C`, Cream `#FDEFE2`, Pink `#E6A6A4`, Pink Deep `#D67F7C`, Card `#FFFBF6`, Peach `#F7E3D0`, Sky `#99D2F3`, Disabled `#E6D9CC`.

### Componentes (`lib/widgets/`)

`TdButton`, `TdChip`, `TdSearchField`, `TdTextField`, `TdPhotoFrame`, `TdIconButton`, `TdQuantityStepper` (modo `compact` no carrinho).

### Carrinho (`lib/cart/`)

- `CartController` — memória; `deliveryFeeAmount = 6.0` para entrega; `removeAt`, `updateQuantity`
- `CartScope`, `DeliveryMode` (pickup/delivery)
- `CartAddedResult` + `CartAddedBanner` — balão 5 s no catálogo, link **Ver carrinho**

### Checkout (`lib/checkout/`)

- `CheckoutValidators` (nome/WhatsApp), `DeliveryAddressValidators` (rua, número, bairro, referência)
- Entrega só Nazaré da Mata - PE (CEP 55.800-000)
- PII só em memória (`CheckoutDraft`); sem persistência nem Mercado Pago no cliente

### Telas (fluxo completo)

| # | Arquivo | Notas |
|---|---------|-------|
| 1 | `home_screen.dart` | Catálogo, balão ao adicionar |
| 2 | `product_screen.dart` | Adicionar → pop com `CartAddedResult` |
| 3 | `cart_screen.dart` | Remover item, entrega R$ 6,00 |
| 4 | `checkout_screen.dart` | Nome, WhatsApp, endereço se entrega |
| 5 | `pix_screen.dart` | QR placeholder, timer, confirmação manual |
| 6 | `confirmation_screen.dart` | Limpa carrinho, voltar à loja |

## Layout web

- Nav inferior no `body` (Column), não `bottomNavigationBar`
- `MaterialApp.builder` com `Scaffold` cream; balão do carrinho é widget overlay no catálogo
- `AppTheme.maxContentWidth` = 430px

## API no cliente

- Web: `apiBaseUrl` = `/api`
- Mobile: `https://tridocuras.com.br/api` (`lib/config.dart`)

## Deploy

```bash
cd /opt/hosting && docker compose up -d --build app1-web
```

Teste em https://tridocuras.com.br (hard refresh após deploy).

## Pendente

Mercado Pago real, `POST /api/orders`, rastreamento de pedidos.
