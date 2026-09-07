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

### Implementado (cliente — 6 telas)

| # | Tela | Resumo |
|---|------|--------|
| 1 | Catálogo | Busca, chips, grade, badge do carrinho, balão ao adicionar item |
| 2 | Produto | Opções, quantidade, Adicionar → catálogo com confirmação |
| 3 | Carrinho | Stepper, **Remover** item, entrega (retirar / receber R$ 6,00) |
| 4 | Checkout | Nome, WhatsApp, endereço (entrega), Pix via Mercado Pago |
| 5 | Pagamento Pix | QR escaneável, copia-e-cola, timer 10 min, confirmação automática |
| 6 | Confirmação | Resumo do pedido, status Pago, voltar à loja |

**Entrega:** apenas Nazaré da Mata - PE (CEP 55.800-000); taxa R$ 6,00 para receber em casa.

**Navegação:** catálogo → produto → carrinho → checkout → Pix → confirmação.

Carrinho e checkout no Flutter; **Gerar Pix** grava o pedido (`POST /api/orders`), gera cobrança Pix no Mercado Pago e exibe QR + copia-e-cola. A confirmação é automática via webhook + polling (`GET /api/orders/{id}`).

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
| Rastreamento de pedidos | UI “em breve” (`GET /api/orders/{id}/tracking` — futuro) |

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
| Checkout / endereço | `frontend/lib/checkout/` |

## Testes (frontend)

| Arquivo | Cobertura |
|---------|-----------|
| `test/cart/cart_controller_test.dart` | Carrinho, taxa de entrega, remoção |
| `test/checkout/checkout_validators_test.dart` | Nome, WhatsApp |
| `test/checkout/delivery_address_validators_test.dart` | Endereço de entrega |
| `test/checkout/order_payload_test.dart` | Payload do POST /orders |
| `test/models/created_order_test.dart` | Parse da resposta da API |
| `test/widget_test.dart` | Smoke do app |

## Mobile

- **Android:** abrir `frontend/` no Android Studio e build APK/AAB
- **iOS:** requer Mac + Xcode (projeto em `frontend/ios/`)
- API mobile: `https://tridocuras.com.br/api` em `frontend/lib/config.dart` (web usa `/api` relativo)

## Documentação

- [Frontend Flutter](frontend/README.md)
- [API Dart Frog](api/README.md)
- Skill Cursor: `frontend/.cursor/skills/tri-docuras-project/SKILL.md`
