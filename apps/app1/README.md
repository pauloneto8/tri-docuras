# Tri Doçuras — App 1

Doceria online especializada em brownies. Cliente multiplataforma (Android, iOS, web) com API Dart e PostgreSQL isolados.

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

Domínio configurado em `/opt/hosting/.env` → `APP1_DOMAIN`.

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
| Tela catálogo | `frontend/lib/screens/home_screen.dart` |
| Tela produto | `frontend/lib/screens/product_screen.dart` |
| Carrinho (memória) | `frontend/lib/cart/` |

### Implementado

**Tela 1 — Catálogo:** wordmark, busca, chips, grade 2 colunas, bottom nav, navegação para produto.

**Tela 2 — Produto:** opções de tamanho/extra, quantidade, total dinâmico, adicionar ao carrinho em memória (badge atualiza no catálogo).

**Tela 3 — Carrinho:** lista de itens, entrega, resumo, finalizar pedido (checkout placeholder).

### Pendente (telas 4–6)

Checkout completo, Pix Mercado Pago, confirmação.

## Mobile

- **Android:** abrir `frontend/` no Android Studio e build APK/AAB
- **iOS:** requer Mac + Xcode (projeto em `frontend/ios/`)
- API mobile: configurar em `frontend/lib/config.dart`

## Documentação

- [Frontend Flutter](frontend/README.md)
- [API Dart Frog](api/README.md)
