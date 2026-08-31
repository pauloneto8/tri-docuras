# Tri Doçuras — Flutter (`tri_docuras`)

App multiplataforma da doceria Tri Doçuras (Android, iOS e web).

**Application ID:** `br.com.tridocuras.app`

## Stack

- Flutter 3.x / Dart 3.12+
- `http` — consumo da API
- `google_fonts` — Lora + Poppins (design system)

## Estrutura

```
lib/
├── main.dart              # MaterialApp + CartScope + tema
├── config.dart            # apiBaseUrl (web: /api, mobile: host)
├── cart/
│   ├── cart_controller.dart   # itens, deliveryMode, subtotal/total
│   ├── cart_item.dart
│   ├── cart_scope.dart        # InheritedWidget para CartController
│   └── delivery_mode.dart     # retirar na loja / receber em casa
├── theme/
│   ├── app_colors.dart    # paleta do design system
│   └── app_theme.dart     # ThemeData + tipografia
├── models/product.dart
├── services/api_service.dart
├── screens/
│   ├── home_screen.dart      # catálogo (tela 1)
│   ├── product_screen.dart   # detalhe do produto (tela 2)
│   ├── cart_screen.dart      # carrinho (tela 3)
│   ├── checkout_screen.dart  # checkout (tela 4)
│   ├── pix_screen.dart       # pagamento Pix (tela 5)
│   └── confirmation_screen.dart # confirmação (tela 6)
├── checkout/
│   ├── checkout_draft.dart
│   ├── checkout_validators.dart
│   ├── order_summary.dart
│   └── whatsapp_input_formatter.dart
└── widgets/
    ├── td_button.dart
    ├── td_chip.dart
    ├── td_icon_button.dart
    ├── td_photo_frame.dart
    ├── td_quantity_stepper.dart
    ├── td_search_field.dart
    └── td_text_field.dart
```

## Design system

Referência: `/root/.cursor/docs/tri-docuras/design-system-tri-docuras.pdf`

Render PNG das páginas (comparação visual): `/root/.cursor/docs/tri-docuras/render/`

### Paleta (`lib/theme/app_colors.dart`)

| Token | Hex | Uso |
|-------|-----|-----|
| Dark | `#412414` | títulos, chip selecionado |
| Brown | `#6A3A23` | texto secundário, anéis da moldura |
| Tan | `#A4653C` | ícones inativos (nav) |
| Cream | `#FDEFE2` | fundo do app |
| Pink | `#E6A6A4` | coração na moldura |
| Pink Deep | `#D67F7C` | CTAs, nav ativo, badge carrinho |
| Success | `#7C9473` | status pago (futuro) |
| Warning | `#C98A3C` | aguardando pagamento (futuro) |
| Card | `#FFFBF6` | fundo dos cards de produto |
| Peach | `#F7E3D0` | chips inativos, círculos do header, preenchimento da moldura |
| Sky | `#99D2F3` | ícone de busca, ícone Pedidos (nav) |
| Disabled | `#E6D9CC` | botão indisponível |

### Tipografia (`lib/theme/app_theme.dart`)

**Importante:** não usar `.merge(lora).merge(poppins)` no `TextTheme` — o segundo `merge` anula os estilos Lora. Os estilos são definidos explicitamente.

| Estilo | Fonte | Tamanho | Uso |
|--------|-------|---------|-----|
| `displayLarge` | Lora Italic 600 | 44px | destaques (display) |
| `displayMedium` | Lora Italic 600 | 24px | wordmark no header |
| `headlineSmall` | Lora 600 | 24px | títulos de seção |
| `titleMedium` | Lora 600 | 15px | nome do produto no card |
| `bodyMedium` | Poppins 400 | 15px | descrições |
| `bodyLarge` | Poppins 600 | 14px | preços |
| `labelSmall` | Poppins 600 | 12px | labels (uppercase no PDF) |

### Componentes (`lib/widgets/`)

| Widget | Descrição |
|--------|-----------|
| `TdButton` | Pill; variantes `primary`, `outline`, `soft`, `disabled`. Texto em caixa normal (não uppercase). Suporta `trailing` (ex.: preço na tela de produto). |
| `TdChip` | Filtro de categoria; selecionado = dark + texto branco; inativo = peach + texto dark. |
| `TdSearchField` | Campo pill branco com sombra; ícone de busca em sky. |
| `TdTextField` | Campo de formulário (cantos 12px); usado no checkout. |
| `TdPhotoFrame` | Moldura assinatura: círculo com dois anéis marrons (`CustomPaint`) + coração rosa no centro; preenchimento peach. Aceita `imageUrl` opcional. |
| `TdIconButton` | Botão circular (header menu, voltar, favorito, carrinho). |
| `TdQuantityStepper` | Seletor `−` / quantidade / `+` com círculos outline brown. Modo `compact` nas linhas do carrinho. |

### Tela 1 — Catálogo (`home_screen.dart`)

Implementada conforme página 4 do PDF (lado esquerdo):

- **Header:** menu (círculo peach) | wordmark Lora Italic centralizado | carrinho (círculo peach) + badge dinâmico (`CartController.itemCount`)
- **Busca:** `TdSearchField` — placeholder "Buscar brownie..."
- **Chips:** Todos / Brownies / Combos
- **Grade:** 2 colunas fixas, cards off-white com moldura circular
- **Navegação:** toque no card ou em "Adicionar" abre a tela de produto
- **Bottom nav:** dentro do `body` (Column), não `Scaffold.bottomNavigationBar`

### Tela 2 — Produto (`product_screen.dart`)

Implementada conforme página 4 do PDF (lado direito):

- **Header:** voltar (←) e favorito (♥) em círculos peach
- **Moldura** grande, nome (Lora), preço `/ unidade`, descrição
- **Opções** (brownies): chips `9x9cm` / `Fatia grande` + toggle `Sem lactose +R$3`
- **Combos:** sem chips de tamanho/extra
- **Quantidade:** stepper (default 2)
- **Rodapé:** `TdButton` "Adicionar" + total dinâmico; grava em `CartController` e volta ao catálogo

### Tela 3 — Carrinho (`cart_screen.dart`)

Implementada conforme página 5 do PDF (lado esquerdo):

- **Header:** voltar + título "Seu carrinho" (Lora)
- **Linhas:** moldura pequena, nome, preço unitário, stepper compacto
- **ENTREGA:** `Retirar na loja` / `Receber em casa` (chips pill)
- **Resumo:** Subtotal, Retirada/Entrega (Grátis), Total
- **Rodapé:** `Finalizar pedido` + total → navega ao checkout
- Ícone do carrinho no catálogo abre esta tela
- Carrinho vazio: mensagem orientando adicionar produtos

### Tela 4 — Checkout (`checkout_screen.dart`)

Implementada conforme página 5 do PDF (lado direito), com validação no cliente:

- **Header:** voltar + título "Finalizar" (Lora)
- **NOME COMPLETO** / **WHATSAPP** — `TdTextField` + validadores (`checkout_validators.dart`); máscara `(11) 91234-5678`
- **RETIRADA / ENTREGA** — card somente leitura (sem formulário de endereço)
- **PAGAMENTO** — card visual "Pix via Mercado Pago" (sem integração)
- **Resumo:** Subtotal e Total a pagar via `CartController`
- **Rodapé:** `Gerar Pix` + total — desabilitado até formulário válido; abre tela 5
- PII só em memória (`CheckoutDraft` por construtor); sem persistência, URL ou logs

### Tela 5 — Pagamento Pix (`pix_screen.dart`)

Implementada conforme página 6 do PDF (lado esquerdo):

- QR visual (placeholder até API Mercado Pago — sem código escaneável falso)
- Total, timer de expiração (10 min), preview do código + COPIAR (integração pendente)
- Status “Aguardando pagamento”, passos 1–3, texto Mercado Pago
- **Já realizei o pagamento** → confirmação (até webhook automático existir)

### Tela 6 — Confirmação (`confirmation_screen.dart`)

Implementada conforme página 6 do PDF (lado direito):

- Pedido confirmado, resumo (#pedido, retirada/entrega, total, status Pago)
- Acompanhar pedido (em breve), Voltar à loja (limpa stack → catálogo)

### Fluxo de navegação

```
HomeScreen ──► ProductScreen ──(Adicionar)──► pop → HomeScreen
HomeScreen ──(ícone carrinho)──► CartScreen ──(Finalizar)──► CheckoutScreen
CheckoutScreen ──(Gerar Pix)──► PixScreen ──(Já realizei o pagamento)──► ConfirmationScreen
```

Estado do carrinho: `CartController` em memória (sem persistência). Badge do header = `itemCount`. Carrinho é limpo na confirmação.

### Pendente (integração)

Pix Mercado Pago real (QR + copia-e-cola via API), webhook de confirmação automática, `POST /api/orders`, rastreamento de pedidos.
## Desenvolvimento

```bash
cd /opt/hosting/apps/app1/frontend
flutter pub get
flutter analyze
flutter test
flutter run -d web-server --web-hostname 0.0.0.0
```

### Android / iOS

```bash
flutter run -d android
flutter run -d ios   # requer Mac
```

Altere `lib/config.dart` para apontar a API ao ambiente de dev.

## Deploy web (VPS)

```bash
cd /opt/hosting
docker compose build app1-web
docker compose up -d app1-web
```

O build usa `ghcr.io/cirruslabs/flutter:stable` e serve em Nginx interno.

## Layout web (importante)

- Nav inferior dentro do `body` (`Column`), não `Scaffold.bottomNavigationBar`
- Fundo cream em `ColoredBox` + `web/index.html` (`#FDEFE2`)
- Conteúdo centralizado: `AppTheme.maxContentWidth` (430px)
- Grade catálogo: `SliverGridDelegateWithFixedCrossAxisCount` com `mainAxisExtent` fixo — evitar `childAspectRatio` baixo no web

## Agent Skills (Cursor)

Skills oficiais Flutter/Dart em `.cursor/skills/` (24 + `tri-docuras-project`).

Invocar: `/flutter-build-responsive-layout` ou `@tri-docuras-project`

## Teste

```bash
curl -s https://tridocuras.example.com/api/products
# Abrir no navegador: https://tridocuras.example.com/
```

Após deploy, use hard refresh (`Ctrl+Shift+R`) para evitar cache do build anterior.
