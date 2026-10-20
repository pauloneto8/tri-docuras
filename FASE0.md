# Tri Doçuras — Fase 0: colocar a loja para vender

Gravado em 19/10/2026. Detalha a Fase 0 do [`PLANO.md`](PLANO.md). É para ser
executado por outro agente, passo a passo, na ordem abaixo.

**Objetivo:** ao final, um cliente real consegue comprar pelo site
(https://tridocuras.com.br), pagar com Pix, ter o pagamento confirmado
sozinho, e a loja recebe o aviso no WhatsApp. Também fica para trás a stack
antiga duplicada, com backup.

**Tempo estimado:** 1 dia de trabalho, dependendo de quando o dono entregar
os itens da seção 1.

---

## 0. Contexto obrigatório (ler antes de tudo)

| Coisa | Onde |
|-------|------|
| Repositório | `/opt/tridocuras` (git, branch `main`, remoto `github.com/pauloneto8/tri-docuras`) |
| Código da loja | `apps/app1/api` (Dart Frog) e `apps/app1/frontend` (Flutter web) |
| Compose **ativo** | `/opt/tridocuras/docker-compose.tridocuras.yml` (projeto `tridocuras`) |
| `.env` ativo | `/opt/tridocuras/.env` (permissão 600, entra via `env_file`) |
| HTTPS / proxy | Caddy do AssistFin: `/opt/assistfin/Caddyfile` → `app-tridocuras:8080` (`/api/*`, `/admin*`) e `app-tridocuras-web:80` (resto) |
| Containers ativos | `app-tridocuras`, `app-tridocuras-web`, `app-tridocuras-db` |
| Volumes ativos | `tridocuras_db`, `tridocuras_uploads` |
| Containers **antigos** (a remover) | `hosting-app1`, `hosting-app1-web`, `hosting-app1-db`, `hosting-app2-db` (este em loop de restart) |
| Volumes antigos (manter 30 dias) | `app1_db_data`, `app1_uploads`, `app2_db_data`, `app2_backups` |

### Regras invioláveis

1. **Nunca** rode `docker compose` com o `docker-compose.yml` antigo da raiz, nem `docker compose down -v` em qualquer arquivo. Sempre use `docker compose -f docker-compose.tridocuras.yml ...` a partir de `/opt/tridocuras`.
2. **Não toque** nos containers do AssistFin: `app-assistfin`, `caddy-assistfin`, `backup-assistfin`, `ollama-assistfin`. Não reinicie o Caddy (não é preciso nesta fase).
3. **Não exiba segredos** (tokens, chaves, senha) no chat, em logs, em commits nem em saídas de comando. Para conferir variáveis, conte ou mostre só o nome (`sed 's/=.*/=<set>/'`).
4. Nenhum segredo entra no git. O `.env` já está no `.gitignore`; confirme antes de cada commit com `git status`.
5. Toda alteração de código vem com teste, e a suíte roda verde antes do deploy:
   - API: `docker run --rm -v /opt/tridocuras/apps/app1/api:/app -w /app dart:stable sh -c "dart pub get && dart test"`
   - Front: `flutter analyze --fatal-infos && flutter test` em `apps/app1/frontend` (se não houver Flutter na VPS, rode via `ghcr.io/cirruslabs/flutter:stable`, como no Dockerfile).
6. Commits pequenos, um por passo, no padrão `tipo(app1): descrição`, terminando com o trailer de coautoria. **Não dê push** sem o dono autorizar.
7. Se algum passo falhar e a correção não for óbvia, **pare e relate** com a saída do erro. Não improvise em produção.

---

## 1. O que o dono precisa entregar (checklist de entrada)

Peça tudo de uma vez, no início. Os passos que dependem de cada item estão indicados.

| # | Item | Usado em |
|---|------|----------|
| E1 | **Access Token de produção** do Mercado Pago (`APP_USR-...`) | 0.6 |
| E2 | **Public Key de produção** (`APP_USR-...`) | 0.6 |
| E3 | **Chave secreta do webhook**: painel MP → Suas integrações → app → Webhooks → Configurar notificações → "Assinatura secreta" | 0.6 |
| E4 | Confirmação de que a conta MP tem **uma chave Pix cadastrada** (sem isso, o MP recusa a criação de cobrança Pix) | 0.6 |
| E5 | **Número real do WhatsApp da loja** (com DDD) | 0.7 |
| E6 | **Chave da API do CallMeBot**, ativada **a partir do mesmo número E5** (instruções em 0.8) | 0.8 |
| E7 | **Fotos** de cada produto visível (lista em 0.9) | 0.9 |
| E8 | Um celular com app de banco para pagar **R$ 1,00** no teste final | 0.10 |

Os passos 0.1 a 0.5 **não dependem** do dono: comece por eles enquanto espera.

---

## 2. Passos

### 0.1 — Pré-voo (somente leitura)

```bash
cd /opt/tridocuras
git status --short            # precisa estar limpo; se não estiver, pare e relate
git log -1 --oneline          # anotar o commit de partida
docker ps --format '{{.Names}}\t{{.Status}}'
docker volume ls --format '{{.Name}}' | grep -E 'trido|app1|app2'
sed 's/=.*/=<set>/' .env      # só nomes
curl -s https://tridocuras.com.br/api/health
```

**Pronto quando:** você confirmou que o estado bate com a tabela da seção 0 e anotou o commit de partida no relatório.

---

### 0.2 — Backup completo do estado atual

```bash
B=/opt/tridocuras/backups/2026-10-19-fase0
mkdir -p "$B" && chmod 700 "$B"

# Bancos (formato custom, restaurável com pg_restore)
docker exec app-tridocuras-db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$B/tridocuras_db.dump"
docker exec hosting-app1-db   sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$B/hosting_app1_db.dump"
# hosting-app2-db está em loop de restart: não há dump; o volume app2_db_data fica preservado.

# Fotos (volumes)
for v in tridocuras_uploads app1_uploads; do
  docker run --rm -v "$v":/data:ro -v "$B":/out alpine tar czf "/out/$v.tgz" -C /data .
done

# Configuração
cp /opt/tridocuras/.env "$B/env.tridocuras" && chmod 600 "$B/env.tridocuras"

ls -la "$B"
```

Confira que `backups/` está no `.gitignore` e, se não estiver, adicione-o (commit `chore(app1): ignora backups locais`).

**Teste de restauração (obrigatório):**

```bash
docker run -d --name restore-test -e POSTGRES_PASSWORD=x postgres:16-alpine
sleep 5
docker cp "$B/tridocuras_db.dump" restore-test:/tmp/d.dump
docker exec restore-test sh -c 'createdb -U postgres t && pg_restore -U postgres -d t /tmp/d.dump && psql -U postgres -d t -Atc "select count(*) from products; select count(*) from orders;"'
docker rm -f restore-test
```

**Pronto quando:** os 5 arquivos existem com tamanho > 0 e o restore lista contagens de `products` e `orders`.
**Se falhar:** não avance para 0.3.

---

### 0.3 — Desligar a stack antiga

O site já é servido pelos containers `app-tridocuras*` via Caddy. Os `hosting-*` não recebem tráfego.

```bash
docker stop hosting-app1 hosting-app1-web hosting-app1-db hosting-app2-db
```

Espere 5 minutos e faça o smoke test:

```bash
curl -s https://tridocuras.com.br/api/health        # status ok, database connected
curl -s -o /dev/null -w '%{http_code}\n' https://tridocuras.com.br/        # 200
curl -s -o /dev/null -w '%{http_code}\n' https://tridocuras.com.br/admin   # 200
curl -s https://assistfin.com.br/health             # AssistFin intacto
```

Se tudo estiver OK, remova os containers (os volumes **ficam**):

```bash
docker rm hosting-app1 hosting-app1-web hosting-app1-db hosting-app2-db
```

Registre no fim deste arquivo, em "Registro de execução": *"Volumes antigos app1_db_data, app1_uploads, app2_db_data, app2_backups preservados; remover a partir de 18/11/2026 com autorização do dono."*

**Rollback:** `docker start <nome>` antes do `rm`. Depois do `rm`, os volumes e os dumps de 0.2 permitem recriar.
**Pronto quando:** `docker ps -a` não mostra mais nenhum `hosting-*` e os quatro curls passam.

---

### 0.4 — Corrigir o bug: webhook repetido faz o status do pedido voltar

**Problema:** `markOrderPaid` em `apps/app1/api/lib/orders.dart` (por volta da linha 384) atualiza com `WHERE public_id = $1 AND status <> 'paid' AND status <> 'cancelled'`. O Mercado Pago reenvia notificações. Se o pedido já estiver `preparing`/`ready`/`completed`, ele volta para `paid` e `paid_at` é sobrescrito, bagunçando a fila e o Financeiro.

**Mudança:**

1. Em `orders.dart`, crie a constante pública e use-a na query:
   ```dart
   /// Únicos status a partir dos quais uma confirmação do Mercado Pago pode
   /// marcar o pedido como pago. Notificações repetidas sobre pedidos já
   /// pagos/em preparo/prontos/concluídos/cancelados são ignoradas.
   const paymentConfirmableStatuses = ['pending_payment'];
   ```
   Troque a cláusula por `WHERE public_id = \$1 AND status = ANY(\$3::text[])`, passando `paymentConfirmableStatuses` como terceiro parâmetro.
2. Quando o `UPDATE` não atualizar nada, registre uma linha de log `print('[mp] pagamento $paymentId ignorado: pedido $publicId não está em pending_payment')`. Siga o estilo de log já usado no arquivo; se não houver nenhum, use `stderr.writeln`.
3. **Teste** (novo arquivo `test/orders_payment_status_test.dart`; a suíte não tem banco):
   - `paymentConfirmableStatuses` é exatamente `['pending_payment']`;
   - para cada um de `paid, preparing, ready, completed, cancelled`, o status **não** está na lista.
4. Rode a suíte da API (regra 5).
5. Commit: `fix(app1): webhook repetido do MP nao regride status do pedido`.

O deploy acontece junto com o 0.5.

**Pronto quando:** a suíte está verde, incluindo os testes novos.

---

### 0.5 — Rede de segurança: confirmar o pagamento também pelo polling

**Problema:** hoje o pedido só vira `paid` pelo webhook. O `GET /api/orders/{id}` (que o app consulta a cada 3 s na tela do Pix) só lê o banco. Se o webhook falhar (URL errada, assinatura errada, MP instável), o cliente paga e fica preso em "Aguardando pagamento".

**Mudança** em `apps/app1/api/routes/api/orders/[id]/index.dart`, com a lógica em `lib/orders.dart`:

1. Crie `Future<Map<String, Object?>> refreshOrderPaymentIfStale(Map<String, Object?> order)`. Se `status == 'pending_payment'`, `mp_payment_id != null` e o throttle permitir, chame `syncOrderPaymentFromMercadoPago(mp_payment_id)`. Se ele retornar `true`, recarregue o pedido com `getOrderByPublicId`. Qualquer exceção é capturada e logada, e devolve o pedido original: **o GET nunca falha por causa do MP**.
2. Throttle em memória, por pedido: no máximo uma consulta ao MP a cada **15 s**. Implemente como uma classe pura `PaymentCheckThrottle` (com `bool shouldCheck(String publicId, DateTime now)` e limpeza de entradas com mais de 1 h), para dar para testar sem relógio real.
3. A rota passa a chamar `refreshOrderPaymentIfStale` antes de serializar.
4. **Testes** em `test/payment_check_throttle_test.dart`: a primeira chamada libera; a segunda dentro de 15 s bloqueia; após 15 s libera; pedidos diferentes são independentes; a limpeza remove entradas antigas.
5. Suíte verde → commit `feat(app1): polling do pedido reconsulta o MP como fallback do webhook`.
6. **Deploy da API** (leva 0.4 e 0.5):
   ```bash
   cd /opt/tridocuras
   docker compose -f docker-compose.tridocuras.yml build app-tridocuras
   docker compose -f docker-compose.tridocuras.yml up -d app-tridocuras
   docker logs --tail 30 app-tridocuras
   curl -s https://tridocuras.com.br/api/health
   ```

**Rollback:** `git revert` dos dois commits, depois build e up de novo.
**Pronto quando:** o health está ok após o deploy e os logs não mostram erro de startup.

---

### 0.6 — Credenciais do Mercado Pago (depende de E1–E4)

1. No `/opt/tridocuras/.env`, adicione ou atualize (sem ecoar os valores):
   ```env
   APP1_MP_ACCESS_TOKEN=<E1>
   APP1_MP_PUBLIC_KEY=<E2>
   APP1_MP_WEBHOOK_SECRET=<E3>
   APP1_MP_USE_TEST=false
   ```
   Confira que `APP1_DOMAIN=tridocuras.com.br` (é dele que sai a `notification_url` enviada ao MP, em `mercado_pago_config.dart`).
   Edite com um editor ou um `cat >>` cujo conteúdo não vá para o log. Depois rode `chmod 600 .env`.
2. Validação básica do token, sem imprimi-lo:
   ```bash
   set -a; . /opt/tridocuras/.env; set +a
   curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $APP1_MP_ACCESS_TOKEN" https://api.mercadopago.com/users/me
   # esperado: 200. 401 = token errado → peça E1 de novo.
   ```
   Confirme também que o token começa com `APP_USR-`: `[ "${APP1_MP_ACCESS_TOKEN#APP_USR-}" != "$APP1_MP_ACCESS_TOKEN" ] && echo prod`.
3. Recrie o container (o `env_file` só é relido com `up -d`):
   ```bash
   docker compose -f docker-compose.tridocuras.yml up -d app-tridocuras
   docker exec app-tridocuras sh -c 'env | grep -c "^APP1_MP_"'   # >= 4
   ```
4. No painel do MP (o dono faz, ou você orienta): a URL de webhook de **produção** deve ser `https://tridocuras.com.br/api/webhooks/mercadopago`, com o evento **Pagamentos** marcado.
5. Teste de assinatura inválida (deve recusar):
   ```bash
   curl -s -w '\n%{http_code}\n' -X POST 'https://tridocuras.com.br/api/webhooks/mercadopago?data.id=123' \
     -H 'Content-Type: application/json' -H 'x-signature: ts=1,v1=deadbeef' -H 'x-request-id: teste' \
     -d '{"type":"payment","data":{"id":"123"}}'
   # esperado: 401 {"error":"Assinatura inválida."}
   ```
6. Opcional: no painel do MP, use "Simular notificação". Uma notificação assinada com um ID inexistente deve retornar **200** com `processed: false`. Se der 401, o segredo E3 está errado.

**Pronto quando:** `users/me` retorna 200, o webhook falso retorna 401 e a simulação do MP (se feita) retorna 200.

---

### 0.7 — WhatsApp real da loja (depende de E5)

1. No `.env`, com E5 normalizado para `55` + DDD + número (13 dígitos para celular):
   ```env
   APP1_STORE_WHATSAPP=55819XXXXXXXX
   APP1_STORE_WHATSAPP_DISPLAY=(81) 9XXXX-XXXX
   ```
2. Recrie a API (`up -d app-tridocuras`) e confira que `curl -s https://tridocuras.com.br/api/config` agora tem `store_whatsapp` e `store_whatsapp_display`.
3. **Fallback do front:** `apps/app1/frontend/lib/config.dart` tem o número falso `5581987654321` / `(81) 98765-4321`. Ele é usado por `lib/store_config_holder.dart` quando a API falha. Troque pelo número real (o número da loja é público, pode ir para o código). Depois rode `grep -rn "98765" apps/app1` para não sobrar nenhuma ocorrência.
4. Front: `flutter analyze --fatal-infos && flutter test` → commit `fix(app1): WhatsApp real da loja no fallback do app`.
5. Deploy do front:
   ```bash
   docker compose -f docker-compose.tridocuras.yml build app-tridocuras-web
   docker compose -f docker-compose.tridocuras.yml up -d app-tridocuras-web
   ```
6. Verificação manual (num navegador anônimo, para evitar o cache): aba **Perfil** → o número exibido é o real → o botão abre o `wa.me/55819...` correto.

**Pronto quando:** a API e o app mostram o número real, e não sobra nenhuma ocorrência do número falso.

---

### 0.8 — Aviso de pedido pago no WhatsApp da loja (CallMeBot, depende de E5/E6)

A API manda o aviso para `APP1_STORE_WHATSAPP` (`whatsapp_notify.dart`). Por isso, **a chave CallMeBot precisa ter sido gerada a partir desse mesmo número**.

1. Instrução ao dono: siga o passo a passo atual em https://www.callmebot.com/blog/free-api-whatsapp-messages/ (adicionar o contato do CallMeBot e enviar a mensagem de autorização do celular da loja). A resposta traz a `apikey` (= E6).
2. Antes de configurar, teste direto (sem expor a chave no log):
   ```bash
   set -a; . /opt/tridocuras/.env; set +a
   curl -s -o /dev/null -w '%{http_code}\n' --get https://api.callmebot.com/whatsapp.php \
     --data-urlencode "phone=$APP1_STORE_WHATSAPP" --data-urlencode "text=Teste Tri Doçuras" \
     --data-urlencode "apikey=<E6>"
   ```
   O dono confirma que recebeu a mensagem.
3. No `.env`:
   ```env
   APP1_WHATSAPP_NOTIFY_ENABLED=true
   APP1_WHATSAPP_PROVIDER=callmebot
   APP1_CALLMEBOT_API_KEY=<E6>
   ```
   Deixe `APP1_WHATSAPP_NOTIFY_CUSTOMER` desligado (exige a Meta Cloud API; isso é da Fase 3).
4. Recrie a API (`up -d app-tridocuras`).

O teste real acontece no 0.10.
**Pronto quando:** a mensagem de teste do passo 2 chegou e as variáveis estão no container.

---

### 0.9 — Fotos dos produtos (depende de E7)

Produtos visíveis hoje (via `curl -s https://tridocuras.com.br/api/products`): **Brownie Tradicional (id 6)**, **Ninho c/ Nutella (2)**, **Brownie c/ Nozes (3)**, **Caixa Presente 4un (4)**, mais os que a API listar no momento.

Especificação das fotos para o dono: **quadradas (1:1)**, de 1000×1000 a 1600×1600 px, JPG ou WebP, **até 5 MB** (limite em `product_images.dart`), fundo claro e o produto centralizado. A moldura do app é circular, então nada importante pode ficar nos cantos.

1. Se vierem maiores ou não quadradas, redimensione e corte num diretório próprio (ex.: com ImageMagick: `convert in.jpg -resize 1200x1200^ -gravity center -extent 1200x1200 -quality 85 out.jpg`).
2. Suba cada uma em https://tridocuras.com.br/admin → **Produtos** → editar → foto. Se o dono preferir fazer sozinho, oriente-o.
3. Verifique:
   ```bash
   curl -s https://tridocuras.com.br/api/products | python3 -c 'import json,sys; [print(p["id"], p["name"], bool(p["image_url"])) for p in json.load(sys.stdin)["products"]]'
   ```
4. Confira no celular, em aba anônima: o catálogo, a tela de produto e o carrinho mostram as fotos sem distorção.

**Pronto quando:** todos os produtos visíveis aparecem com `True` e ficam bem na moldura.

---

### 0.10 — Teste ponta a ponta com dinheiro real (depende de 0.4–0.9 e E8)

1. No `/admin` → Produtos, crie **"Teste Pix"** (R$ 1,00, categoria qualquer, sem destaque, **visível**). Um produto oculto não pode ser comprado, porque a API recusa `available = false`.
2. No celular, em https://tridocuras.com.br (aba anônima): adicione "Teste Pix" com quantidade 1, escolha **Retirar na loja**, preencha nome e WhatsApp reais do dono e toque em **Gerar Pix**.
   - Se aparecer erro de Pix, veja `docker logs --tail 50 app-tridocuras`. Causa provável: falta de chave Pix na conta (E4) ou token errado.
3. Pague com o app do banco (copia e cola).
4. Verificações, todas obrigatórias:

   | Verificação | Esperado |
   |-------------|----------|
   | Tela do Pix | Vai sozinha para **Pedido confirmado** em até ~15 s |
   | `docker logs app-tridocuras` | Chegou um `POST /api/webhooks/mercadopago` com 200 (ou a confirmação veio pelo polling do 0.5; anote qual dos dois) |
   | WhatsApp da loja | Chegou o aviso do CallMeBot com pedido, itens e total |
   | `/admin` → Pedidos | O pedido aparece como **Pago** na fila |
   | `/admin` → Financeiro (Hoje) | R$ 1,00 contabilizado |
   | Aba **Pedidos** do app | A timeline mostra "Pagamento confirmado" |

5. **Teste do bug 0.4:** no `/admin`, mova o pedido para **Em preparo**. Se o painel do MP permitir reenviar a notificação desse pagamento, reenvie. Depois confira que o pedido **continua Em preparo** e que o log mostra a linha "ignorado". Se o MP não permitir reenvio, registre isso; a cobertura fica com o teste unitário.
6. **Limpeza:**
   - `/admin` → Produtos → "Teste Pix" → desmarque **Visível no app**;
   - `/admin` → cancele o pedido de teste (assim ele sai do Financeiro);
   - o dono devolve o R$ 1,00 pelo app do Mercado Pago (Atividade → pagamento → Devolver). O estorno automático é da Fase 1.

**Pronto quando:** todas as linhas da tabela do passo 4 deram o esperado, a limpeza foi feita e o catálogo público não mostra mais o "Teste Pix".

---

### 0.11 — Fechamento

1. `git status` limpo, exceto pelos commits desta fase. Rode `git log --oneline <commit-de-partida>..HEAD` e cole a saída no relatório.
2. Atualize `apps/app1/README.md` só no que esta fase mudou: o compose ativo (`docker-compose.tridocuras.yml`), o caminho `/opt/tridocuras`, o fallback de confirmação por polling e o CallMeBot ligado. A reescrita completa da documentação é a Fase 4. Commit: `docs(app1): estado apos fase 0`.
3. Preencha o "Registro de execução" abaixo.
4. Pergunte ao dono se pode dar `git push origin main`. O CI roda no push.

---

## 3. Relatório final esperado (o que o agente entrega ao dono)

- Commit de partida e lista de commits feitos.
- Tabela dos passos 0.1–0.11 com ✅ / ❌ e uma linha de observação cada.
- Resultado do teste ponta a ponta (tabela do 0.10.4), incluindo se a confirmação veio pelo webhook ou pelo polling.
- Pendências que ficaram (ex.: o MP não permite reenvio de notificação, uma foto faltando).
- Lembrete: os volumes antigos podem ser removidos a partir de 18/11/2026; o backup da fase está em `/opt/tridocuras/backups/2026-10-19-fase0/` e **ainda não tem cópia fora da VPS** (isso é a Fase 1.1).

---

## 4. Registro de execução

_(preenchido pelo agente executor)_

| Data | Passo | Resultado | Observação |
|------|-------|-----------|------------|
| 19/10 | 0.1 | ✅ | Partida: b557cd8. Árvore limpa (só PLANO.md/FASE0.md novos) |
| 19/10 | 0.2 | ✅ | `backups/2026-10-19-fase0/`; restore ok (use `pg_restore --no-owner`); ambos os bancos com 0 pedidos; volumes de uploads vazios (sem fotos) |
| 19/10 | 0.3 | ✅ | hosting-app1, -web, -db e app2-db parados e removidos; volumes app1_db_data, app1_uploads, app2_db_data, app2_backups preservados; remover a partir de 18/11/2026 com autorização do dono. Sobraram `hosting-nginx` e `hosting-app2` em estado Created (nunca iniciados), fora do plano, não removidos |
| 19/10 | 0.4 | ✅ | Commit 6acb4e5 (junto com 0.5); 2 testes novos |
| 19/10 | 0.5 | ✅ | Commit 6acb4e5; 4 testes novos (suíte: 64 verdes); API em produção, health ok |
| 19/10 | 0.6 | ✅ | Segredo configurado (64 chars) e no container; webhook com assinatura falsa retorna 401. Histórico: token de produção válido (users/me 200)... (nota antiga: Token de produção válido (users/me 200); token e chave pública no container. **APP1_MP_WEBHOOK_SECRET ausente** (linha 9 do .env sem `=` nem valor): assinatura do webhook segue desligada (webhook falso retorna 200, não 401) — RESOLVIDO acima) |
| 20/10 | 0.7 | ⚠️ parcial | Sem mudança de código. Continua pendente só a conferência visual no app (Perfil → WhatsApp) |
| 19/10 | 0.7 | ⚠️ parcial | Número falso removido do app (commit abaixo); sem número na API os botões de WhatsApp ficam ocultos; front em produção; 36 testes Flutter verdes. **E5 recebido**: 5581996918192, gravado no .env; `/api/config` devolve número e display; falta só a verificação visual no app (Perfil → WhatsApp) |
| | 0.8–0.10 | ⏳ | Aguardam E5–E8 do dono  |
