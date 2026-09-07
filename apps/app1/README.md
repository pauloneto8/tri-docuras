# Tri Doçuras — App 1

Doceria online especializada em brownies. Cliente multiplataforma (Android, iOS, web) com API Dart e PostgreSQL isolados.

**Produção:** https://tridocuras.com.br

## Componentes

| Serviço | Container | Descrição |
|---------|-----------|-----------|
| Frontend | `hosting-app1-web` | Flutter web (build estático + Nginx interno) |
| API | `hosting-app1` | Dart Frog na porta interna 8080 |
| Banco | `hosting-app1-db` | PostgreSQL 16 (rede `app1_internal`) |

## Roteamento (Nginx)

| Caminho | Destino |
|---------|---------|
| `/` | Flutter web (`app1-web`) |
| `/api/*` | Dart Frog (`app1:8080`) |
| `/admin` | Painel de pedidos da loja (`app1:8080`) |

Domínio em `/opt/hosting/.env` → `APP1_DOMAIN` (`tridocuras.com.br`). HTTPS via Let's Encrypt (`/opt/hosting/certs`).

## API

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/api/health` | Status da API + ping PostgreSQL |
| GET | `/api/products` | Catálogo (`available = true` no app) |
| POST | `/api/orders` | Criar pedido + gerar Pix (Mercado Pago) |
| GET | `/api/orders/{id}` | Status do pedido (`pending_payment` / `paid`) |
| POST | `/api/orders/{id}/pix` | Regenerar cobrança Pix (se expirada) |
| POST | `/api/webhooks/mercadopago` | Webhook de confirmação de pagamento |
| GET | `/api/orders/{id}/tracking` | Timeline de rastreamento (cliente) |
| GET | `/admin` | Painel web da loja |
| POST | `/api/admin/session` | Login do painel |
| GET | `/api/admin/orders` | Lista pedidos (autenticado) |
| POST | `/api/admin/orders/{id}/status` | Atualiza status do pedido |
| GET | `/api/admin/products` | Lista produtos (inclui ocultos) |
| POST | `/api/admin/products` | Cria produto |
| PUT | `/api/admin/products/{id}` | Atualiza produto |

### Catálogo em produção (set/2026)

| ID | Nome | Preço | Exibido no app |
|----|------|-------|----------------|
| 4 | Brownie Tradicional | R$ 12,00 | Sim |
| 5 | Ninho c/ Nutella | R$ 15,00 | Sim |
| 6 | Brownie c/ Nozes | R$ 14,00 | Sim |
| 7 | Caixa Presente (4un) | R$ 48,00 | Sim |
| 1–3 | Brownies legado (seed antigo) | R$ 12–15 | Não (`available = false`) |

Categorias: `brownies`, `combos`.

## Estado atual do produto

### Implementado (app cliente)

#### Fluxo de compra (6 telas)

| # | Tela | Resumo |
|---|------|--------|
| 1 | Catálogo | Busca, chips, grade, menu ☰, badge do carrinho, balão ao adicionar |
| 2 | Produto | Opções, favorito ♥, quantidade, Adicionar → catálogo |
| 3 | Carrinho | Stepper, remover item, entrega (retirar / receber R$ 6,00) |
| 4 | Checkout | Nome, WhatsApp, endereço, Pix via Mercado Pago |
| 5 | Pagamento Pix | QR, copia-e-cola, confirmação automática |
| 6 | Confirmação | Resumo, rastreamento, voltar à loja |

#### Bottom navigation (4 abas)

| Aba | Tela | Resumo |
|-----|------|--------|
| Início | Catálogo | Grade de produtos |
| Pedidos | `OrderLookupScreen` | Consulta `TD-0001` + timeline |
| Favoritos | `FavoritesScreen` | Lista persistida (`shared_preferences`) |
| Perfil | `ProfileScreen` | Info da loja, entrega, WhatsApp |

**Menu ☰** (catálogo): bottom sheet `StoreMenuSheet` com horário, entrega e sobre a loja.

**Entrega:** apenas Nazaré da Mata - PE (CEP 55.800-000); taxa R$ 6,00 para receber em casa.

**Navegação compra:** catálogo → produto → carrinho → checkout → Pix → confirmação → (opcional) rastreamento.

**Favoritos:** coração na tela do produto; IDs salvos localmente no dispositivo/navegador.

**Contato da loja:** `AppConfig.storeWhatsApp` em `frontend/lib/config.dart` (ajustar número real).

Carrinho e checkout no Flutter; **Gerar Pix** grava o pedido (`POST /api/orders`), gera cobrança Pix no Mercado Pago e exibe QR + copia-e-cola. A confirmação é automática via webhook + polling (`GET /api/orders/{id}`).

### Ciclo de vida do pedido

| Status | Quem define | Significado |
|--------|-------------|-------------|
| `pending_payment` | Sistema | Aguardando Pix |
| `paid` | Webhook MP | Pagamento confirmado |
| `preparing` | Painel `/admin` | Em preparo |
| `ready` | Painel `/admin` | Pronto para retirada/entrega |
| `completed` | Painel `/admin` | Retirado ou entregue |

Transições no painel: `paid` → `preparing` → `ready` → `completed` (com atalhos permitidos, ex.: `paid` → `ready`).

### Variáveis de ambiente (`/opt/hosting/.env`)

| Variável | Obrigatória | Uso |
|----------|-------------|-----|
| `APP1_DB_*` | Sim | PostgreSQL |
| `APP1_MP_ACCESS_TOKEN` | Para Pix real | Access Token de produção |
| `APP1_MP_TEST_*` / `APP1_MP_USE_TEST` | Não | Sandbox Mercado Pago |
| `APP1_ADMIN_PASSWORD` | Para painel | Senha de https://tridocuras.com.br/admin |
| `APP1_DOMAIN` | Sim | Domínio público + webhook MP |

WhatsApp exibido no Perfil do app: `frontend/lib/config.dart` → `storeWhatsApp` (não é variável de `.env`).

Modelo completo: [`../../.env.example`](../../.env.example) na raiz do hosting.

### Mercado Pago (Pix)

Credenciais em `/opt/hosting/.env` (não versionar):

```env
# Produção — pagamentos reais (apps bancários)
APP1_MP_ACCESS_TOKEN=APP_USR-...

# Teste — sandbox (não funciona em bancos reais)
APP1_MP_TEST_ACCESS_TOKEN=TEST-...
APP1_MP_TEST_PUBLIC_KEY=TEST-...
APP1_MP_USE_TEST=false
```

| Variável | Uso |
|----------|-----|
| `APP1_MP_ACCESS_TOKEN` | Access Token de **produção** (`APP_USR-...`) |
| `APP1_MP_TEST_ACCESS_TOKEN` | Access Token de **teste** (`TEST-...`) |
| `APP1_MP_TEST_PUBLIC_KEY` | Public Key de teste (reservado para uso futuro no cliente) |
| `APP1_MP_USE_TEST` | `true` = sandbox; `false` = produção (padrão em produção) |

No painel [Suas integrações](https://www.mercadopago.com.br/developers/panel/app):

1. Ative **credenciais de produção** (site: `https://tridocuras.com.br`)
2. Configure webhook: `https://tridocuras.com.br/api/webhooks/mercadopago`
3. Habilite notificações de **pagamentos**

Documentação MP: [Credenciais](https://www.mercadopago.com.br/developers/pt/docs/your-integrations/credentials)

```bash
cd /opt/hosting
docker compose build app1 app1-web && docker compose up -d app1 app1-web
```

**Importante:** credenciais de teste geram Pix simulado — **não** são aceitos em apps bancários reais. Para pagar de verdade, use `APP1_MP_USE_TEST=false` com token de produção.

### Pendente

| Item | Estado |
|------|--------|
| CRUD de produtos no `/admin` | Implementado |
| Fotos no catálogo | Futuro |
| Notificação WhatsApp ao confirmar pagamento | Futuro |

### Painel da loja

**URL:** https://tridocuras.com.br/admin

1. Defina `APP1_ADMIN_PASSWORD` no `/opt/hosting/.env` (senha forte; não versionar).
2. Reinicie a API: `docker compose up -d app1`.
3. Acesse `/admin`, informe a senha e gerencie a fila.

O painel lista pedidos com itens, endereço, total e link para WhatsApp do cliente. Atualização automática a cada 30 s.

**Abas:** Fila (`active` = pagos + preparo + prontos), Pagos, Em preparo, Prontos, Aguardando Pix, Concluídos.

```bash
# Trocar senha: edite APP1_ADMIN_PASSWORD no .env e reinicie app1
cd /opt/hosting && docker compose up -d app1
```

### Rastreamento (cliente)

| Onde | Como |
|------|------|
| App — aba **Pedidos** | Digite `TD-0001` e consulte a timeline |
| Tela de confirmação | Botão **Acompanhar pedido** |
| API | `GET /api/orders/{id}/tracking` |

A timeline reflete os mesmos status do painel da loja (polling a cada 15 s no app).

## Operações

```bash
cd /opt/hosting

# Status
docker compose ps app1 app1-web app1-db

# Health (produção)
curl -s https://tridocuras.com.br/api/health
curl -s https://tridocuras.com.br/api/products | head -c 200

# Logs
docker compose logs -f app1 app1-web

# Rebuild após mudança no frontend
docker compose build app1-web && docker compose up -d app1-web

# Rebuild após mudança na API
docker compose build app1 && docker compose up -d app1
```

Após deploy do frontend, use hard refresh no navegador (`Ctrl+Shift+R`).

## Desenvolvimento local

```bash
# API (hot reload)
cd /opt/hosting/apps/app1/api
dart pub global activate dart_frog_cli
dart_frog dev

# Flutter web
cd /opt/hosting/apps/app1/frontend
flutter pub get
flutter analyze
flutter test
flutter run -d web-server --web-hostname 0.0.0.0
```

## Design system

Paleta cream/chocolate/rosa, fontes Lora + Poppins.

| Recurso | Caminho |
|---------|---------|
| PDF completo | `/root/.cursor/docs/tri-docuras/design-system-tri-docuras.pdf` |
| Renders PNG (6 páginas) | `/root/.cursor/docs/tri-docuras/render/` |
| Tokens e tema | `frontend/lib/theme/` |
| Widgets base | `frontend/lib/widgets/` |
| Telas | `frontend/lib/screens/` |
| Carrinho (memória) | `frontend/lib/cart/` |
| Favoritos (local) | `frontend/lib/favorites/` |
| Checkout / endereço | `frontend/lib/checkout/` |

## Testes

### API (`apps/app1/api`)

```bash
docker run --rm -v /opt/hosting/apps/app1/api:/app -w /app dart:stable sh -c "dart pub get && dart test"
```

| Arquivo | Cobertura |
|---------|-----------|
| `test/mercado_pago_client_test.dart` | Status de pagamento MP |
| `test/admin_orders_test.dart` | Labels e transições de status |
| `test/order_tracking_test.dart` | Timeline do cliente |

### Frontend

| Arquivo | Cobertura |
|---------|-----------|
| `test/cart/cart_controller_test.dart` | Carrinho, taxa de entrega, remoção |
| `test/checkout/checkout_validators_test.dart` | Nome, WhatsApp |
| `test/checkout/delivery_address_validators_test.dart` | Endereço de entrega |
| `test/checkout/order_payload_test.dart` | Payload do POST /orders |
| `test/models/created_order_test.dart` | Parse da resposta (pedido + Pix) |
| `test/models/order_tracking_test.dart` | Parse da timeline |
| `test/favorites/favorites_controller_test.dart` | Toggle de favoritos |
| `test/widget_test.dart` | Smoke do app |

## Mobile

- **Android:** abrir `frontend/` no Android Studio e build APK/AAB
- **iOS:** requer Mac + Xcode (projeto em `frontend/ios/`)
- API mobile: `https://tridocuras.com.br/api` em `frontend/lib/config.dart` (web usa `/api` relativo)
- WhatsApp da loja: ajustar `storeWhatsApp` no mesmo `config.dart`

## Documentação

- [Frontend Flutter](frontend/README.md)
- [API Dart Frog](api/README.md)
- Skill Cursor: `frontend/.cursor/skills/tri-docuras-project/SKILL.md`
