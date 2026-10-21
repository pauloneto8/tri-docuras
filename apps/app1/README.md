# Tri Doçuras — App 1

Doceria online especializada em brownies. Cliente multiplataforma (Android, iOS, web) com API Dart e PostgreSQL isolados.

**Produção:** https://tridocuras.com.br

> **Atualizado em 21/10/2026.** Fases 0 e 1 do [`PLANO.md`](../../PLANO.md)
> concluídas, exceto os itens que dependem do dono (ver [Pendente](#pendente)).
> Contas de cliente: Fases A a D feitas, C e D sem deploy ainda
> ([`CONTAS.md`](../../CONTAS.md)). Monitoramento e operação:
> [`docs/MONITORAMENTO.md`](../../docs/MONITORAMENTO.md) e
> [`docs/OPERACAO.md`](../../docs/OPERACAO.md).

## Componentes

Compose ativo: `/opt/tridocuras/docker-compose.tridocuras.yml` (projeto `tridocuras`).
O `docker-compose.yml` da raiz é antigo e não deve ser usado.

| Serviço | Container | Descrição |
|---------|-----------|-----------|
| Frontend | `app-tridocuras-web` | Flutter web (build estático + Nginx interno, com CSP) |
| API | `app-tridocuras` | Dart Frog na porta interna 8080 |
| Banco | `app-tridocuras-db` | PostgreSQL 16 (rede interna) |
| Backup | `backup-tridocuras` | `pg_dump` + `tar` dos uploads, 03:30 (Recife); 14 diários + 8 semanais em `/opt/tridocuras/backups/tridocuras/`. Script em `scripts/backup-tridocuras.sh` |

## Roteamento

HTTPS e roteamento ficam no Caddy do AssistFin (`/opt/assistfin/Caddyfile`), não neste repositório.

| Caminho | Destino |
|---------|---------|
| `/` | Flutter web (`app-tridocuras-web:80`) |
| `/api/*` | Dart Frog (`app-tridocuras:8080`) |
| `/admin` | Painel da loja — pedidos e catálogo (`app-tridocuras:8080`) |

Domínio em `.env` → `APP1_DOMAIN` (`tridocuras.com.br`).

## API

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/api/health` | Status da API + ping PostgreSQL. 200 com banco ok, 503 sem banco |
| GET | `/api/products` | Catálogo (`available = true` no app) |
| POST | `/api/orders` | Criar pedido + gerar Pix (Mercado Pago). Limite: 10 por hora por IP |
| GET | `/api/orders/{id}` | Status do pedido. Em `pending_payment`, reconsulta o MP no máximo a cada 15 s (rede de segurança do webhook) |
| POST | `/api/orders/{id}/pix` | Regenerar cobrança Pix (se expirada). Limite: 10 por hora por IP |
| POST | `/api/webhooks/mercadopago` | Webhook de confirmação de pagamento |
| GET | `/api/orders/{id}/tracking` | Timeline de rastreamento (cliente) |
| GET | `/admin` | Painel web da loja |
| POST | `/api/admin/session` | Login do painel (`email` + `password`; só senha no modo legado). Limite: 5 tentativas a cada 15 min por IP |
| GET | `/api/admin/me` | Usuário logado e papel |
| GET | `/api/admin/orders/{id}/events` | Histórico de status do pedido: quem mudou, quando e de/para |
| GET/POST | `/api/admin/users` | Lista e cria usuários do painel (só dono) |
| PUT | `/api/admin/users/{id}` | Edita nome, papel, ativo e senha; invalida as sessões do usuário (só dono) |
| GET | `/api/admin/orders` | Lista pedidos (filtros: `status`, `search`, `from`, `to`) |
| POST | `/api/admin/orders/{id}/status` | Atualiza status. Cancelar pedido pago exige `refund: true` (estorna o Pix no MP) ou `refund: false` (cancela sem estorno). Status `expired` é automático |
| GET | `/api/admin/products` | Lista produtos (inclui ocultos) + categorias |
| POST | `/api/admin/products` | Cria produto |
| PUT | `/api/admin/products/{id}` | Atualiza produto |
| GET/POST | `/api/admin/categories` | Lista / cria categorias |
| PUT/DELETE | `/api/admin/categories/{id}` | Edita / remove categoria |
| GET | `/api/admin/finance/report` | Relatório de faturamento (`from`, `to`) |
| GET/PUT | `/api/admin/settings` | Configurações da loja: taxa de entrega, loja aberta e aviso (tabela `store_settings`, linha única) |
| POST | `/api/customers` | Cadastro de cliente (e-mail e senha) |
| POST | `/api/customers/session` | Login do cliente |
| GET/PUT | `/api/customers/me` | Perfil do cliente logado |
| GET | `/api/customers/me/orders` | Pedidos do cliente logado |
| GET/PUT | `/api/customers/me/favorites` | Favoritos do cliente logado |
| POST | `/api/customers/me/password` | Trocar a senha do cliente |

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
| Favoritos | `FavoritesScreen` | Sem conta: no aparelho. Com conta: no servidor |
| Perfil | `ProfileScreen` | Info da loja, entrega, WhatsApp |

**Menu ☰** (catálogo): bottom sheet `StoreMenuSheet` com horário, entrega e sobre a loja.

**Entrega:** apenas Nazaré da Mata - PE (CEP 55.800-000); taxa R$ 6,00 para receber em casa.

**Navegação compra:** catálogo → produto → carrinho → checkout → Pix → confirmação → (opcional) rastreamento.

**Favoritos:** coração na tela do produto. Sem conta, os IDs ficam no dispositivo/navegador. Logado, ficam na conta (`/api/customers/me/favorites`).

**Contato da loja:** vem de `GET /api/config` (`APP1_STORE_WHATSAPP` no `.env`); o app não embute número e esconde os botões de WhatsApp se a API não informar.

Carrinho e checkout no Flutter; **Gerar Pix** grava o pedido (`POST /api/orders`), gera cobrança Pix no Mercado Pago e exibe QR + copia-e-cola. A confirmação é automática via webhook + polling (`GET /api/orders/{id}`).

### Implementado (painel `/admin`)

| Seção | Função |
|-------|--------|
| **Pedidos** | Fila operacional, filtros por status, busca por ID/cliente, filtro por período, WhatsApp do cliente, avanço de status e cancelamento |
| **Produtos** | Criar, editar preço/descrição, destaque, ocultar do catálogo (`available`) e CRUD de categorias |
| **Financeiro** | Faturamento do período (dia/7 dias/mês/personalizado): faturamento, nº de pedidos, ticket médio, taxas de entrega, série diária e vendas por produto |

Pix em **produção** (`APP1_MP_USE_TEST=false`); webhook MP configurado em `https://tridocuras.com.br/api/webhooks/mercadopago`.

**Fotos:** upload no painel **Produtos**; exibidas no app via `image_url`.

### Ciclo de vida do pedido

| Status | Quem define | Significado |
|--------|-------------|-------------|
| `pending_payment` | Sistema | Aguardando Pix |
| `paid` | Webhook MP | Pagamento confirmado |
| `preparing` | Painel `/admin` | Em preparo |
| `ready` | Painel `/admin` | Pronto para retirada/entrega |
| `completed` | Painel `/admin` | Retirado ou entregue |
| `cancelled` | Painel `/admin` | Cancelado (fora do faturamento) |

Transições no painel: `paid` → `preparing` → `ready` → `completed` (com atalhos permitidos, ex.: `paid` → `ready`). Qualquer pedido não concluído pode ser cancelado (`cancelled`), de forma irreversível.

### Variáveis de ambiente (`/opt/tridocuras/.env`)

| Variável | Obrigatória | Uso |
|----------|-------------|-----|
| `APP1_DB_*` | Sim | PostgreSQL |
| `APP1_MP_ACCESS_TOKEN` | Para Pix real | Access Token de produção (`APP_USR-...`) |
| `APP1_MP_PUBLIC_KEY` | Recomendado | Public Key de produção |
| `APP1_MP_CLIENT_ID` / `APP1_MP_CLIENT_SECRET` | Opcional | OAuth / integrações legadas (não usados no Pix atual) |
| `APP1_MP_TEST_*` / `APP1_MP_USE_TEST` | Não | Sandbox Mercado Pago |
| `APP1_ADMIN_PASSWORD` | Para painel | Senha de https://tridocuras.com.br/admin. Sem usuários no banco, ela sozinha abre o painel (modo legado) |
| `APP1_ADMIN_EMAIL` | Recomendado | E-mail do dono. Na primeira subida, com o banco sem usuários, cria o dono com este e-mail e a senha acima |
| `APP1_ADMIN_SECRET` | Recomendado | Chave que assina os tokens do painel. Se ausente, usa a senha |
| `APP1_DOMAIN` | Sim | Domínio público + webhook MP |

WhatsApp exibido no Perfil do app: `frontend/lib/config.dart` → `storeWhatsApp` (não é variável de `.env`).

Modelo completo: [`../../.env.example`](../../.env.example) na raiz deste repositório.

### Mercado Pago (Pix)

Credenciais em `/opt/tridocuras/.env` (não versionar):

```env
# Produção — pagamentos reais (apps bancários)
APP1_MP_PUBLIC_KEY=APP_USR-...
APP1_MP_ACCESS_TOKEN=APP_USR-...
APP1_MP_CLIENT_ID=...
APP1_MP_CLIENT_SECRET=...

# Teste — sandbox (não funciona em bancos reais)
APP1_MP_TEST_ACCESS_TOKEN=TEST-...
APP1_MP_TEST_PUBLIC_KEY=TEST-...
APP1_MP_USE_TEST=false
```

| Variável | Uso |
|----------|-----|
| `APP1_MP_ACCESS_TOKEN` | Access Token de **produção** (`APP_USR-...`) |
| `APP1_MP_PUBLIC_KEY` | Public Key de **produção** |
| `APP1_MP_CLIENT_ID` / `APP1_MP_CLIENT_SECRET` | Par OAuth (reservado; Pix usa só o token) |
| `APP1_MP_TEST_ACCESS_TOKEN` | Access Token de **teste** (`TEST-...`) |
| `APP1_MP_TEST_PUBLIC_KEY` | Public Key de teste (reservado para uso futuro no cliente) |
| `APP1_MP_USE_TEST` | `true` = sandbox; `false` = produção (padrão em produção) |

No painel [Suas integrações](https://www.mercadopago.com.br/developers/panel/app):

1. Ative **credenciais de produção** (site: `https://tridocuras.com.br`)
2. Configure webhook: `https://tridocuras.com.br/api/webhooks/mercadopago`
3. Habilite notificações de **pagamentos**

Documentação MP: [Credenciais](https://www.mercadopago.com.br/developers/pt/docs/your-integrations/credentials)

```bash
cd /opt/tridocuras
docker compose -f docker-compose.tridocuras.yml build app-tridocuras app-tridocuras-web && docker compose -f docker-compose.tridocuras.yml up -d app-tridocuras app-tridocuras-web
```

**Importante:** credenciais de teste geram Pix simulado — **não** são aceitos em apps bancários reais. Para pagar de verdade, use `APP1_MP_USE_TEST=false` com token de produção.

### Pendente

Estado em 21/10/2026 (implementação pausada; sem mudanças de código desde 20/10). Detalhe no [`PLANO.md`](../../PLANO.md) (seção 5) e no [`FASE0.md`](../../FASE0.md) (seção 4).

- **Depende do dono:** conferir o WhatsApp no app (Perfil → WhatsApp); chave CallMeBot para o aviso à loja; fotos dos produtos (`image_url`); teste ponta a ponta com dinheiro real (FASE0 0.8 a 0.10); destino da cópia do backup fora da VPS; decisões da Fase 2.4 (horários, antecedência, limite por faixa); se a encomenda consome estoque; horários e CEPs; logo para os ícones do PWA; foto do brownie para a `og:image`; conteúdo do aviso de alergênicos; decisão sobre a Meta API (mensagem automática ao cliente); revisão jurídica dos Termos de Compra (cancelamento e arrependimento).
- **Monitoramento:** uptime externo ([`MONITORAMENTO.md`](../../docs/MONITORAMENTO.md)).
- **Fase 2, operação (no ar desde 20/10):** configurações da loja, usuários do painel, histórico de status e estoque. Variações por produto (2.6) feitas, sem deploy. Pendente: pronta entrega × encomenda (2.4), que aguarda as decisões do dono.
- **Fase 3, cliente e marca (sem deploy, parcial):** PWA, SEO, status para o cliente (falta a mensagem automática), páginas legais, acabamento de UX (falta o aviso de alergênicos) e painel com cara de produto.
- **Contas de cliente:** Fases A a D feitas (C e D sem deploy ainda).
- **Fase 4:** migrações versionadas, testes de integração, testes de widget e métricas feitos (sem deploy, exceto integração e widgets). Pendente: restante da 4.6 (docs), teste do webhook do Mercado Pago na suíte de integração e decisão sobre `apps/app2`.

### Contato da loja no app

O número do WhatsApp vem de `GET /api/config` (variável `APP1_STORE_WHATSAPP` no `.env`). O app usa fallback em `config.dart` se a API falhar.

### Notificação WhatsApp (loja)

> **Status (20/10/2026):** não ativada em produção. Falta a chave do CallMeBot,
> que é do dono (FASE0 0.7 e 0.8).

Quando um Pix é confirmado, a API pode avisar automaticamente o WhatsApp da loja.

**CallMeBot** (mais simples — recomendado para começar):

1. Adicione o contato CallMeBot no WhatsApp e obtenha sua API key em [callmebot.com](https://www.callmebot.com/)
2. Configure no `/opt/tridocuras/.env`:

```env
APP1_WHATSAPP_NOTIFY_ENABLED=true
APP1_WHATSAPP_PROVIDER=callmebot
APP1_STORE_WHATSAPP=5581999999999   # WhatsApp da loja (DDI 55 + DDD)
APP1_CALLMEBOT_API_KEY=sua-chave
```

3. `docker compose -f docker-compose.tridocuras.yml up -d app-tridocuras`

**Meta WhatsApp Cloud API** (alternativa):

```env
APP1_WHATSAPP_NOTIFY_ENABLED=true
APP1_WHATSAPP_PROVIDER=meta
APP1_STORE_WHATSAPP=5581999999999
APP1_WHATSAPP_ACCESS_TOKEN=...
APP1_WHATSAPP_PHONE_NUMBER_ID=...
```

A mensagem inclui pedido, cliente, itens, total e link do painel. Idempotente (`whatsapp_notified_at` no banco).

### Notificação WhatsApp (cliente)

**No app:** após pagar, botão **Enviar comprovante no WhatsApp** na tela de confirmação (abre conversa com a loja).

**Automática (opcional, Meta Cloud API):**

```env
APP1_WHATSAPP_NOTIFY_CUSTOMER=true
APP1_WHATSAPP_PROVIDER=meta
APP1_WHATSAPP_CUSTOMER_TEMPLATE=order_paid   # template aprovado na Meta
APP1_WHATSAPP_CUSTOMER_TEMPLATE_LANG=pt_BR
```

Template com 3 parâmetros no corpo: nome do cliente, ID do pedido, total formatado.

### Painel da loja

**URL:** https://tridocuras.com.br/admin

1. Defina `APP1_ADMIN_PASSWORD` no `/opt/tridocuras/.env` (senha forte; não versionar).
2. Reinicie a API: `docker compose -f docker-compose.tridocuras.yml up -d app-tridocuras`.
3. Acesse `/admin`, informe a senha e gerencie pedidos e produtos.

#### Aba Pedidos

Lista pedidos com itens, endereço, total e link para WhatsApp do cliente. Atualização automática a cada 30 s.

**Filtros:** Fila (`active` = pagos + preparo + prontos), Pagos, Em preparo, Prontos, Aguardando Pix, Concluídos.

#### Aba Produtos

CRUD do catálogo sem rebuild do app:

| Campo | Descrição |
|-------|-----------|
| Nome / descrição | Exibidos no app |
| Preço | Em reais (ex.: `12.00`) |
| Categoria | Escolhida entre as categorias cadastradas |
| Estoque | Quantidade disponível. Em branco = sem controle. O pedido reserva a quantidade ao ser criado; cancelar ou deixar expirar devolve ao estoque |
| Destaque | Aparece primeiro no catálogo |
| Visível no app | `available` — desmarque para ocultar sem excluir |

O botão **Categorias** abre o CRUD: nome, ordem e visibilidade. Categorias padrão `brownies` e `combos` são criadas no primeiro start; exclusões exigem mover os produtos antes. As categorias ativas viram os chips do catálogo no app (`GET /api/config`).

Alterações refletem em `GET /api/products` na próxima consulta do app.

**Código:** `api/lib/admin_products.dart`, `api/lib/admin_categories.dart`, rotas `/api/admin/products` e `/api/admin/categories`, UI em `admin_panel_html.dart`.

#### Aba Financeiro

Relatório de leitura sobre os pedidos **pagos** (`paid`, `preparing`, `ready`, `completed`), no fuso `America/Recife`:

| Métrica | Descrição |
|---------|-----------|
| Faturamento | Soma de `total` no período |
| Pedidos pagos | Quantidade no período |
| Ticket médio | Faturamento ÷ pedidos |
| Taxas de entrega | Soma de `delivery_fee` |
| Faturamento por dia | Série diária |
| Vendas por produto | Quantidade e receita por item |

Períodos: **Hoje**, **7 dias**, **Este mês** ou intervalo personalizado. Pedidos `cancelled` e `pending_payment` ficam fora.

**Código:** `api/lib/finance.dart`, rota `GET /api/admin/finance/report`.

```bash
# Trocar senha: edite APP1_ADMIN_PASSWORD no .env e reinicie app1
cd /opt/tridocuras && docker compose -f docker-compose.tridocuras.yml up -d app-tridocuras
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
cd /opt/tridocuras

# Status
docker compose -f docker-compose.tridocuras.yml ps app-tridocuras app-tridocuras-web app-tridocuras-db

# Health (produção)
curl -s https://tridocuras.com.br/api/health
curl -s https://tridocuras.com.br/api/products | head -c 200

# Logs
docker compose -f docker-compose.tridocuras.yml logs -f app-tridocuras app-tridocuras-web

# Rebuild após mudança no frontend
docker compose -f docker-compose.tridocuras.yml build app-tridocuras-web && docker compose -f docker-compose.tridocuras.yml up -d app-tridocuras-web

# Rebuild após mudança na API
docker compose -f docker-compose.tridocuras.yml build app-tridocuras && docker compose -f docker-compose.tridocuras.yml up -d app-tridocuras
```

Após deploy do frontend, use hard refresh no navegador (`Ctrl+Shift+R`).

## Desenvolvimento local

```bash
# API (hot reload)
cd /opt/tridocuras/apps/app1/api
dart pub global activate dart_frog_cli
dart_frog dev

# Flutter web
cd /opt/tridocuras/apps/app1/frontend
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
| Admin produtos | `api/lib/admin_products.dart` |

## Testes

As duas suítes rodam no CI (push na `main` e pull requests) e são herméticas:
não dependem de `.env` nem de variáveis do processo.

### API (`apps/app1/api`)

```bash
docker run --rm -v /opt/tridocuras/apps/app1/api:/app -w /app dart:stable sh -c "dart pub get && dart test"
```

Variáveis de ambiente que a API lê (`APP1_ADMIN_PASSWORD`, `APP1_MP_*`,
`APP1_STORE_WHATSAPP`, …) são acessadas por `Env.get` (`api/lib/env.dart`).
`Platform.environment` é imutável e não pode ser substituído, então os testes
usam `Env.override({...})` / `Env.reset()` para controlar o ambiente — inclusive
para simular "nada configurado" (`Env.override({})`).

> Ao adicionar código que leia env, passe por `Env.get` e **não** por
> `Platform.environment` direto: o CI roda a suíte duas vezes, com o ambiente
> limpo e com todas as variáveis de app1 poluídas, justamente para detectar
> teste que dependa do ambiente do processo.

| Arquivo | Cobertura |
|---------|-----------|
| `test/admin_auth_test.dart` | Sessão do painel: HMAC do token, expiração, adulteração, senha não configurada |
| `test/admin_orders_test.dart` | Labels, transições de status e cancelamento |
| `test/admin_products_test.dart` | Validação do CRUD de produtos |
| `test/finance_test.dart` | Período do relatório, ticket médio e status de receita |
| `test/mercado_pago_client_test.dart` | Status de pagamento MP |
| `test/mercado_pago_webhook_test.dart` | Assinatura do webhook (manifest, HMAC, opt-in da secret) |
| `test/app_public_config_test.dart` | Config pública da loja e link `wa.me` |
| `test/order_tracking_test.dart` | Timeline do cliente |
| `test/product_images_test.dart` | Validação de upload de fotos |
| `test/whatsapp_notify_test.dart` | Montagem das mensagens de WhatsApp |

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
| `test/orders/order_history_controller_test.dart` | Histórico de pedidos no aparelho |
| `test/widget_test.dart` | Smoke do app |

### CI (GitHub Actions)

| Workflow | Gate |
|----------|------|
| [`.github/workflows/app1-tests.yml`](../../.github/workflows/app1-tests.yml) | `dart test` na API, em 2 variantes de ambiente (limpo e poluído) |
| [`.github/workflows/app1-frontend-tests.yml`](../../.github/workflows/app1-frontend-tests.yml) | `flutter analyze --fatal-infos` + `flutter test` |

Rodam em push na `main` e em pull request, restritos aos caminhos do app1.

> A API ainda não passa em `dart analyze`: o `dart_frog_lint` gera ~235 infos
> de estilo (doc comments, limite de 80 colunas) pré-existentes. Por isso o
> workflow da API usa `dart test` como gate, sem `dart analyze`. O frontend já
> está limpo e analysis entra como gate.

## Mobile

- **Android:** build de release assinado com a keystore própria (`android/app/tridocuras-release.jks`, alias `tridocuras`; senha em `android/key.properties` — ambos **ignorados** pelo git).
  ```bash
  cd /opt/tridocuras/apps/app1/frontend
  flutter build apk --release          # APK assinado
  flutter build appbundle --release    # AAB para a Play Store
  ```
- **Backup obrigatório:** a keystore **não pode ser perdida** (sem ela não há atualização do app publicado). Guarde `tridocuras-release.jks` + `key.properties` fora do servidor.
- **Play Store:** o app **ainda não está publicado**. Pendentes: conta de desenvolvedor Google Play (US$ 25), AAB, Play App Signing, ficha (ícones, screenshots, descrição, política de privacidade) e revisão.
- **iOS:** requer Mac + Xcode (projeto em `frontend/ios/`)
- **API mobile:** `https://tridocuras.com.br/api` em `frontend/lib/config.dart` (web usa `/api` relativo)
- **WhatsApp da loja:** ajustar `storeWhatsApp` no mesmo `config.dart`

## Documentação

- [Frontend Flutter](frontend/README.md)
- [API Dart Frog](api/README.md)
- Skill Cursor: `frontend/.cursor/skills/tri-docuras-project/SKILL.md`
