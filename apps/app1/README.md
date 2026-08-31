# Tri Doçuras — App 1

Doceria online especializada em brownies. Cliente multiplataforma (Android, iOS, web) com API Dart e PostgreSQL isolados.

**Produção:** https://tridocuras.com.br

## Componentes

| Serviço | Container | Descrição |
|---------|-----------|-----------|
| Frontend | `hosting-app1-web` | Flutter web (build estático + Nginx) |
| API | `hosting-app1` | Dart Frog na porta interna 8080 |
| Banco | `hosting-app1-db` | PostgreSQL 16 |

## Roteamento (Nginx)

| Caminho | Destino |
|---------|---------|
| `/` | Flutter web (`app1-web`) |
| `/api/*` | Dart Frog (`app1:8080`) |

Domínio configurado em `/opt/hosting/.env` → `APP1_DOMAIN` (`tridocuras.com.br`).

## API

- `GET /api/health` — status da API e conexão com o banco
- `GET /api/products` — catálogo (brownies + combos)

Produtos seed: Brownie Tradicional, Ninho c/ Nutella, Brownie c/ Nozes, Caixa Presente (4un).

## Desenvolvimento local

```bash
# API (hot reload)
cd /opt/hosting/apps/app1/api
dart pub global activate dart_frog_cli
dart_frog dev

# Flutter web
cd /opt/hosting/apps/app1/frontend
flutter pub get
flutter run -d web-server --web-hostname 0.0.0.0
```

## Deploy no VPS

```bash
cd /opt/hosting
docker compose up -d --build app1 app1-web
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

### Implementado (telas 1–6)

| # | Tela | Resumo |
|---|------|--------|
| 1 | Catálogo | Busca, chips, grade, badge do carrinho, balão ao adicionar item |
| 2 | Produto | Opções, quantidade, Adicionar → catálogo com confirmação |
| 3 | Carrinho | Stepper, **Remover** item, entrega (retirar / receber R$ 6,00) |
| 4 | Checkout | Nome, WhatsApp, endereço (entrega), Pix visual, Gerar Pix |
| 5 | Pagamento Pix | QR placeholder, timer 10 min, confirmação manual |
| 6 | Confirmação | Resumo do pedido, status Pago, voltar à loja |

**Entrega:** apenas Nazaré da Mata - PE (CEP 55.800-000); taxa R$ 6,00 para receber em casa.

**Navegação:** catálogo → produto → carrinho → checkout → Pix → confirmação.

### Pendente (integração)

Pix Mercado Pago real (QR + webhook), `POST /api/orders`, rastreamento de pedidos.

## Mobile

- **Android:** abrir `frontend/` no Android Studio e build APK/AAB
- **iOS:** requer Mac + Xcode (projeto em `frontend/ios/`)
- API mobile: `https://tridocuras.com.br/api` em `frontend/lib/config.dart`

## Documentação

- [Frontend Flutter](frontend/README.md)
- [API Dart Frog](api/README.md)
