---
name: tri-docuras-project
description: Tri Doçuras Flutter app conventions, design system, Docker deploy, and API integration. Use when editing tri_docuras, Tri Doçuras, brownies catalog, or files under apps/app1/frontend.
paths: lib/**,web/**,pubspec.yaml,android/**,ios/**
---

# Tri Doçuras — projeto Flutter

## Stack

- App: `/opt/hosting/apps/app1/frontend` (`tri_docuras`)
- API: Dart Frog em `/opt/hosting/apps/app1/api` — `GET /api/products`, `GET /api/health`
- Web deploy: `docker compose build app1-web` em `/opt/hosting`
- Design system PDF: `/root/.cursor/docs/tri-docuras/design-system-tri-docuras.pdf`
- Renders PNG: `/root/.cursor/docs/tri-docuras/render/`

## Design system (v1)

### Paleta (`lib/theme/app_colors.dart`)

Dark `#412414`, Brown `#6A3A23`, Tan `#A4653C`, Cream `#FDEFE2`, Pink `#E6A6A4`, Pink Deep `#D67F7C`, Card `#FFFBF6`, Peach `#F7E3D0`, Sky `#99D2F3`, Disabled `#E6D9CC`.

### Tipografia (`lib/theme/app_theme.dart`)

Lora Italic (wordmark `displayMedium`, produtos `titleMedium`), Lora (headings), Poppins (corpo, preços, botões).

**Não** usar `.merge(lora).merge(poppins)` no `TextTheme` — define estilos Lora e Poppins explicitamente.

### Componentes (`lib/widgets/`)

- `TdButton` — pill; variantes `primary`, `outline`, `soft`, `disabled`; sem uppercase
- `TdChip` — selecionado dark/white; inativo peach/dark
- `TdSearchField` — pill branco, ícone sky
- `TdTextField` — formulário cantos 12px (checkout)
- `TdPhotoFrame` — moldura circular (dois anéis brown + coração pink), preenchimento peach
- `TdIconButton` — botão circular (menu, voltar, favorito, carrinho)
- `TdQuantityStepper` — seletor quantidade; modo `compact` no carrinho

### Carrinho (`lib/cart/`)

`CartController` (memória), `CartScope`, `DeliveryMode` (pickup/delivery).

### Checkout (`lib/checkout/`)

`CheckoutValidators` (nome/WhatsApp), `CheckoutDraft` (PII só em memória), `WhatsAppInputFormatter`. Sem persistência, logs ou query params com PII. Sem chaves Mercado Pago no cliente.

### Telas

| # | Arquivo | Status |
|---|---------|--------|
| 1 | `home_screen.dart` | Catálogo — badge, busca, chips, grade, nav no body |
| 2 | `product_screen.dart` | Produto — opções, stepper, Adicionar + total |
| 3 | `cart_screen.dart` | Carrinho — linhas, ENTREGA, resumo, Finalizar |
| 4 | `checkout_screen.dart` | Nome, WhatsApp, retirada, Pix visual, Gerar Pix |
| 5 | `pix_screen.dart` | Placeholder (sem QR/código fake) |

Navegação: card/Adicionar → produto; ícone carrinho → carrinho; Finalizar → checkout; Gerar Pix → Pix.

## Layout web

- Não usar `Scaffold.bottomNavigationBar` — barra inferior no `body` (Column)
- Fundo cream: `ColoredBox` + `web/index.html` (`#FDEFE2`)
- `AppTheme.maxContentWidth` = 430px
- Grade: `SliverGridDelegateWithFixedCrossAxisCount`, `mainAxisExtent` fixo (~268)

## API no cliente

- Web: `apiBaseUrl` = `/api` (`lib/config.dart`)
- Mobile: URL do host de produção; alterar para dev local se necessário

## Deploy

```bash
cd /opt/hosting
docker compose up -d --build app1-web   # só frontend
docker compose up -d --build app1      # API
```

Teste no domínio configurado em `APP1_DOMAIN` (hard refresh após deploy).

## Plataformas

- Web: build no VPS via Docker (Flutter image)
- Android: projeto `android/` — build local com Android Studio
- iOS: projeto `ios/` — requer Mac + Xcode

## Pendente (PDF)

Telas 5–6: Pix Mercado Pago real, confirmação. API: pedidos + Mercado Pago.
