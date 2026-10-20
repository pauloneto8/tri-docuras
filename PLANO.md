# Tri Doçuras — plano para finalizar e profissionalizar

Gravado em 19/10/2026. Escopo: **app1** (loja + API + painel). O app2 deste
repositório é uma cópia antiga do AssistFin e está fora do escopo; o
AssistFin de produção mora em `/opt/assistfin`.

Decisões do dono (19/10):

| Tema | Decisão |
|------|---------|
| Pagamento | Mercado Pago Pix; o dono **já tem as credenciais de produção** |
| Canais | **Web + PWA** (sem Play Store / iOS por enquanto) |
| Operação | Pronta entrega **e** encomenda com data; **controle de estoque**; **várias pessoas** no painel |
| Stack antiga `hosting-*` | **Pode descartar** (fazer backup final antes) |

---

## 1. Avaliação (estado em 19/10/2026)

### O que está bom

- Fluxo completo de compra: catálogo → produto → carrinho → checkout → Pix → confirmação → rastreamento.
- O servidor recalcula preços (o cliente não manda preço); valores em `NUMERIC(10,2)` no banco.
- Token do painel com HMAC + expiração; comparação em tempo constante; webhook do MP com assinatura opcional e reconsulta do pagamento na API oficial.
- A API pública não expõe nome, WhatsApp nem endereço (`orderToPublicJson`).
- Testes herméticos (58 na API e 33 no Flutter) e CI no GitHub Actions.
- Design system próprio aplicado (paleta, Lora/Poppins, componentes `Td*`).

### Problemas encontrados, por gravidade

**Bloqueadores (a loja não vende hoje)**

1. **O Pix não funciona em produção.** O `/opt/tridocuras/.env` só tem `APP1_DOMAIN`, `APP1_DB_*`, `APP1_ADMIN_PASSWORD` e `APP1_MP_USE_TEST=false`. Faltam `APP1_MP_ACCESS_TOKEN`, `APP1_MP_PUBLIC_KEY` e `APP1_MP_WEBHOOK_SECRET`. Todo pedido sai com `pix_error`.
2. **WhatsApp falso.** `frontend/lib/config.dart` tem `5581987654321` / `(81) 98765-4321`, e `APP1_STORE_WHATSAPP` não está no `.env` (o `/api/config` não devolve número). O cliente que tocar em "falar com a loja" cai num número inexistente.
3. **Produtos sem foto.** Todos os produtos têm `image_url: null`.

**Bugs**

4. **Um webhook repetido faz o status voltar.** `markOrderPaid` (`api/lib/orders.dart:383`) só filtra `status <> 'paid' AND status <> 'cancelled'`. Se o MP reenviar a notificação (ele reenvia) depois que a loja moveu o pedido para `preparing`/`ready`/`completed`, o pedido volta para `paid` e `paid_at` é sobrescrito. Correção: `WHERE status = 'pending_payment'`.
5. **Pedido cancelado depois de pago não tem fluxo de estorno.** O painel cancela, o dinheiro fica no MP e ninguém é avisado.
6. **Pedidos `pending_payment` nunca expiram.** Ficam para sempre na base e na aba "Aguardando Pix".
7. **CORS lê `Platform.environment` direto** (`routes/_middleware.dart`), contrariando a regra do próprio README (usar `Env.get`).

**Segurança e operação**

8. **Nenhum backup do banco da loja.** O AssistFin tem `backup-assistfin`; o `app-tridocuras-db` não tem nada. As fotos (volume `uploads`) também não têm backup.
9. **Login do painel sem limite de tentativas** e com uma senha única para todos; não há registro de quem mudou cada pedido.
10. **`POST /api/orders` sem limite de requisições.** Qualquer um pode criar milhares de pedidos e cobranças Pix.
11. **Duas stacks rodando ao mesmo tempo:** `hosting-app1`, `hosting-app1-web` e `hosting-app1-db` (sobras) junto com `app-tridocuras*` (a ativa, atrás do Caddy do AssistFin). O `hosting-app2-db` reinicia em loop.
12. **Sem CSP nem cache correto no front.** O Caddy (`/opt/assistfin/Caddyfile`) não manda CSP (a CSP citada no `pubspec.yaml` era do Nginx antigo), e o `frontend/nginx.conf` não diferencia cache de `index.html`/`flutter_bootstrap.js` dos assets. É por isso que o README manda dar "Ctrl+Shift+R" após o deploy.
13. **Sem monitoramento:** ninguém é avisado se a API cair ou se o webhook falhar.

**Produto e profissionalismo**

14. **Regras fixas no código** (frontend e backend): taxa de entrega R$ 6, área (Nazaré da Mata), adicional sem lactose R$ 3, tamanhos `9x9cm`/`Fatia grande`, horário. Mudar qualquer uma exige deploy.
15. **Sem horário de funcionamento real** nem estado de loja aberta/fechada. Não há agendamento (encomenda com data) nem estoque.
16. **Sem política de privacidade nem termos (LGPD).** O app coleta nome, WhatsApp e endereço.
17. **PWA incompleto:** o `manifest.json` usa a cor `#5D4037` (marrom padrão do template), não a paleta da marca. Não há tela de instalar, ícones da marca revisados nem Open Graph para links compartilhados no WhatsApp.
18. **O cliente não é avisado de mudança de status** (só se abrir a aba Pedidos). O aviso automático ao cliente depende de Meta Cloud API + template aprovado.
19. **Documentação desatualizada:** todos os READMEs apontam para `/opt/hosting`, Nginx e o `docker-compose.yml` antigo; a skill `tri-docuras-project` lista como pendentes itens que já existem.
20. **Lint da API:** cerca de 235 infos no `dart analyze`, por isso ele não é gate no CI.

---

## 2. Plano

As fases são sequenciais. Dentro de cada fase, os itens são independentes, salvo indicação.
Regras para quem executar:

- Todo deploy é feito via `docker compose -f docker-compose.tridocuras.yml` em `/opt/tridocuras`, **nunca** via o `docker-compose.yml` antigo.
- Mudança de schema é uma migração numerada em `appMigrations` (`api/lib/db.dart`), aplicada uma vez e registrada em `schema_migrations` (`api/lib/migrations.dart`). A versão 1 é o `ensureSchema` atual, idempotente, e não se edita. Dentro de uma migração, use `ADD COLUMN IF NOT EXISTS` e `CREATE TABLE IF NOT EXISTS` mesmo assim.
- Toda leitura de env passa por `Env.get`.
- Cada item novo vem com teste na suíte hermética. CI verde antes do deploy.
- Commits por item, no padrão `tipo(app1): descrição`.

### Fase 0 — Colocar a loja para vender (bloqueadores) · ~1 dia

| # | Item | Pronto quando |
|---|------|---------------|
| 0.1 | **Backup do estado atual:** `pg_dump` do `app-tridocuras-db` e do `hosting-app1-db`, mais um `tar` do volume de uploads, guardados fora dos containers (ex.: `/opt/tridocuras/backups/2026-10-19/`). | Os arquivos existem e o dump restaura num Postgres descartável. |
| 0.2 | **Desligar a stack antiga:** `docker stop` + `docker rm` de `hosting-app1`, `hosting-app1-web`, `hosting-app1-db` e `hosting-app2-db`. Os volumes `app1_db_data`/`app1_uploads`/`app2_*` ficam **por 30 dias** e só depois são removidos (anotar a data aqui). | `docker ps` mostra só `app-tridocuras*` do lado da loja; o site continua no ar. |
| 0.3 | **Credenciais do MP** (o dono fornece): `APP1_MP_ACCESS_TOKEN`, `APP1_MP_PUBLIC_KEY` e `APP1_MP_WEBHOOK_SECRET` no `/opt/tridocuras/.env`. No painel do MP, conferir a URL do webhook `https://tridocuras.com.br/api/webhooks/mercadopago` com o evento *pagamentos*. | Um Pix real de R$ 1 (produto de teste oculto) é pago, o pedido vira `paid` sozinho via webhook, e um webhook com assinatura errada recebe 401. |
| 0.4 | **Corrigir o bug 4:** `markOrderPaid` passa a filtrar `status = 'pending_payment'`. Teste: um webhook repetido sobre um pedido `preparing` não altera nada. | Teste novo verde. |
| 0.5 | **WhatsApp real:** `APP1_STORE_WHATSAPP` e `APP1_STORE_WHATSAPP_DISPLAY` no `.env`; trocar o fallback do `config.dart` pelo número real (ou remover o fallback e esconder o botão se `/api/config` falhar). | `/api/config` devolve o número, e o botão do Perfil abre a conversa certa. |
| 0.6 | **Fotos:** o dono envia as fotos; subir pelo painel. | Todos os produtos visíveis têm `image_url`. |
| 0.7 | **Notificação da loja:** ligar o CallMeBot (`APP1_WHATSAPP_NOTIFY_ENABLED=true`, provider `callmebot`, chave do dono). | Um Pix pago gera uma mensagem no WhatsApp da loja. |

### Fase 1 — Confiabilidade e segurança · ~2–3 dias

| # | Item | Pronto quando |
|---|------|---------------|
| 1.1 | **Backup diário automático** do `app-tridocuras-db` e do volume `uploads`: um container `backup-tridocuras` no compose (mesmo modelo do `backup-assistfin`), com retenção de 14 diários + 8 semanais e cópia fora da VPS (o mesmo destino do AssistFin, se houver). | O dump do dia aparece; um restore de teste foi documentado em `docs/OPERACAO.md`. |
| 1.2 | **Limite de requisições:** login do painel (5 tentativas a cada 15 min por IP), `POST /api/orders` e `POST /orders/{id}/pix` (ex.: 10 por hora por IP + WhatsApp). Pode ser em memória (1 réplica) ou via `rate_limit` do Caddy. O IP vem de `X-Forwarded-For` confiável, já que o Caddy está na frente. | Testes cobrem o 429; a 6ª senha errada é bloqueada. |
| 1.3 | **Expirar pedidos não pagos:** uma tarefa periódica na API (ou na consulta) marca como `expired` os `pending_payment` com `pix_expires_at` vencido há mais de 24 h. Adicionar o status `expired` à timeline e aos filtros. | Os pedidos velhos somem da fila "Aguardando Pix". |
| 1.4 | **Cancelamento de pedido pago:** ao cancelar um pedido `paid`/`preparing`/`ready`, o painel pergunta se deve estornar e chama `POST /v1/payments/{id}/refunds` no MP; grava `refunded_at`. O cancelamento sem estorno fica registrado como tal. | Teste com cliente MP fake; o painel mostra "Estornado". |
| 1.5 | **Monitoramento:** um uptime externo (UptimeRobot/BetterStack gratuito) em `/api/health`, com alerta no e-mail/WhatsApp do dono. Logar falhas do webhook e do MP com o ID do pedido. | O alerta chega ao derrubar o container de propósito. |
| 1.6 | **Headers e cache do front:** no Caddy, CSP (`default-src 'self'; img-src 'self' data: blob:; connect-src 'self'; script-src 'self' 'wasm-unsafe-eval'`, a ajustar ao Flutter web), `X-Frame-Options DENY` e `Permissions-Policy`. No `frontend/nginx.conf`, `Cache-Control: no-cache` em `index.html`, `flutter_bootstrap.js`, `flutter_service_worker.js` e `manifest.json`, e cache longo nos assets com hash. | Não precisa mais de hard refresh após o deploy; o site carrega sem erro de CSP no console. |
| 1.7 | **Pequenos ajustes:** CORS via `Env.get`; resolver os lints da API e ligar `dart analyze` como gate no CI. | CI com analyze verde. |

### Fase 2 — Operação real da loja (decisões do dono) · ~1–1,5 semana

Ordem recomendada: 2.1 → 2.2 → 2.3 → 2.4 → 2.5 (2.3 e 2.4 dependem de 2.1).

| # | Item | Pronto quando |
|---|------|---------------|
| 2.1 | **Configurações da loja no banco** (tabela `store_settings`, editável no painel numa aba "Loja"): taxa de entrega, cidade/CEPs atendidos, adicional sem lactose, tamanhos, horários por dia da semana, mensagem de aviso, loja aberta/fechada manual. O `/api/config` passa a expor tudo, e o Flutter **para de ter essas regras fixas** (o backend continua sendo a fonte de verdade do preço). | Mudar a taxa no painel muda o carrinho e o total do pedido sem deploy. |
| 2.2 | **Usuários do painel:** tabela `admin_users` (nome, e-mail, hash **argon2id/bcrypt**, papel `dono`/`atendente`, ativo). Login por e-mail + senha; token assinado com uma chave própria (`APP1_ADMIN_SECRET`), não com a senha. O dono gerencia os usuários; o atendente não vê o Financeiro nem os Usuários. Migração: o primeiro login com a `APP1_ADMIN_PASSWORD` antiga cria o usuário dono e força a troca. | Duas pessoas logam com contas próprias; o atendente recebe 403 no relatório financeiro. |
| 2.3 | **Histórico de status (auditoria):** tabela `order_events` (pedido, de, para, usuário, data, observação). Aparece no detalhe do pedido no painel. | Toda mudança de status mostra quem fez e quando. |
| 2.4 | **Pronta entrega × encomenda:** no checkout, o cliente escolhe entre "o quanto antes" (só com a loja aberta) e "agendar" (data e faixa de horário). As faixas vêm de `store_settings`: antecedência mínima (ex.: 24 h), dias e horários disponíveis e **limite de pedidos por faixa**. O pedido guarda `fulfillment_type` e `scheduled_for`. O painel ganha uma visão "Agenda" (pedidos por dia) e destaca os pedidos do dia. Com a loja fechada, o checkout só permite agendar. | Uma faixa lotada some do seletor; o backend rejeita um horário inválido ou lotado mesmo com o cliente adulterado. |
| 2.5 | **Estoque:** coluna `stock` em `products` (nulo = ilimitado), editável no painel. **Reserva na criação do pedido** (`UPDATE ... SET stock = stock - $q WHERE stock >= $q`, na mesma transação do insert), **devolução** ao expirar ou cancelar. Com estoque 0, o produto aparece como "Esgotado" no app, com o botão desabilitado. Para encomendas, avaliar se o estoque vale só para pronta entrega (perguntar ao dono antes; ver §3). | Teste de concorrência: dois pedidos simultâneos pela última unidade → um passa e o outro recebe 409. |
| 2.6 | **Variações por produto:** tamanhos e adicionais (com preço) cadastrados por produto no painel, em vez de `9x9cm`/`Fatia grande`/sem lactose fixos para todo brownie. | Um produto sem variação não mostra chips; o preço do pedido inclui o adicional, calculado no servidor. |

### Fase 3 — Experiência do cliente e marca · ~1 semana

| # | Item | Pronto quando |
|---|------|---------------|
| 3.1 | **PWA de verdade:** `manifest.json` com as cores da marca (`#FDEFE2`/`#412414`), ícones e maskable refeitos a partir do logo, `start_url: "/"`, `id`, `screenshots`; convite "Instalar app" (Android: `beforeinstallprompt`; iOS: instrução de "Adicionar à Tela de Início"). | Lighthouse PWA "installable"; o ícone na tela inicial fica correto. |
| 3.2 | **SEO e compartilhamento:** `<title>`, `description`, Open Graph/Twitter card com foto do brownie, `robots.txt`, `sitemap.xml` e favicon da marca. Um texto mínimo no `index.html` para pré-visualização (o Flutter web não renderiza para robôs). | O link colado no WhatsApp mostra a imagem e a descrição. |
| 3.3 | **Status para o cliente:** link de rastreamento enviado na confirmação (`/pedido/TD-XXXX?t=<token>`), com token por pedido para não depender de um ID sequencial fácil de adivinhar. Se o dono aprovar o custo da Meta Cloud API (ver §3), mensagens automáticas em `preparing`/`ready`. Senão, um botão no painel "Avisar cliente" abre o `wa.me` com a mensagem pronta. | O cliente recebe o link e acompanha o pedido sem digitar o número. |
| 3.4 | **Páginas legais:** Política de Privacidade (LGPD: quais dados, para quê, por quanto tempo, contato), Termos de Compra (prazo, cancelamento, estorno, alergênicos) e caixa de consentimento no checkout. A razão social/CNPJ ou CPF de quem vende vai no rodapé (o dono fornece). | Links no Perfil e no checkout; o pedido grava `accepted_terms_at`. |
| 3.5 | **Acabamento de UX:** esqueleto de carregamento no catálogo, estados de erro com "Tentar de novo", mensagem clara quando a loja estiver fechada, aviso de alergênicos por produto, acessibilidade (rótulos `Semantics`, contraste dos textos tan/sky em cream e alvos de toque ≥ 48 px). | Uma revisão manual nas 6 telas + aba Pedidos com a rede lenta (DevTools "Slow 4G"). |
| 3.6 | **Painel com cara de produto:** responsivo para celular (é onde a loja opera), som/vibração em pedido novo pago, impressão/compartilhamento da comanda do pedido e exportação CSV no Financeiro. | Um atendente opera a fila pelo celular sem zoom. |

### Fase 4 — Base para crescer · contínuo

| # | Item |
|---|------|
| 4.1 | Migrações versionadas (tabela `schema_migrations` + arquivos numerados) no lugar do `ensureSchema` crescente. |
| 4.2 | Testes de integração da API contra um Postgres real no CI (service container), cobrindo criar pedido → webhook → status → estoque. |
| 4.3 | Teste de widget/golden das telas principais e um teste ponta a ponta do checkout com o MP mockado. |
| 4.4 | Documentação reescrita para a realidade atual: `/opt/tridocuras`, `docker-compose.tridocuras.yml`, Caddy em `/opt/assistfin/Caddyfile`. Criar `docs/OPERACAO.md` (deploy, rollback, restore de backup, trocar credenciais) e atualizar a skill `tri-docuras-project`. Remover o `docker-compose.yml`, o `nginx/` e os `scripts/` antigos e decidir se `apps/app2` sai deste repositório. |
| 4.5 | Métricas simples: pedidos por dia, conversão (pedido criado → pago) e taxa de expiração do Pix, no Financeiro. |
| 4.6 | (Futuro) Cupom de desconto, programa de fidelidade, Play Store via TWA reaproveitando o PWA. |

---

## 3. Perguntas ainda abertas (responder antes da fase indicada)

| Fase | Pergunta |
|------|----------|
| 0 | Qual é o número real do WhatsApp da loja? As fotos dos produtos já existem? |
| 0 | Para o CallMeBot: qual número recebe os avisos de pedido pago? |
| 1 | Onde guardar a cópia do backup fora da VPS (mesmo destino do AssistFin, Google Drive, outro)? |
| 1 | Um pedido cancelado depois de pago sempre gera estorno integral, ou às vezes vira crédito ou troca? |
| 2 | Quais são os horários reais (por dia da semana) e quantos pedidos/unidades a cozinha aguenta por faixa ou por dia? |
| 2 | Qual a antecedência mínima de uma encomenda? Qual o prazo máximo (ex.: até 30 dias)? |
| 2 | O estoque vale só para pronta entrega (encomenda é produzida sob demanda), ou para os dois? |
| 2 | Quantas pessoas usam o painel e quem pode ver o Financeiro? |
| 2 | Entrega continua só em Nazaré da Mata com taxa única, ou entram bairros ou cidades com taxas diferentes? |
| 3 | Vende como pessoa física ou com CNPJ/MEI? (Entra nos termos, no rodapé e na conta do MP.) |
| 3 | Aceita pagar a Meta Cloud API (por conversa) para avisar o cliente automaticamente, ou fica o botão "Avisar cliente" no painel? |
| 3 | O logo/ícone atual é o definitivo? Há arquivo vetorial? |

---

## 4. Ordem de entrega sugerida

1. **Fase 0** num único dia → a loja passa a vender de verdade.
2. **Fase 1** na mesma semana → dá para dormir tranquilo (backup, alertas, estorno).
3. **Fase 2** → o app passa a refletir a operação real (agenda, estoque, equipe).
4. **Fase 3** → marca, PWA, LGPD e acabamento: o app fica "profissional" para divulgar.
5. **Fase 4** em paralelo, conforme o tempo permitir.

---

## 5. Status de execução (atualizado em 20/10/2026, implementação pausada)

Os commits estão no `main` (`git log --oneline`). Só o que não está
concluído aparece como pendente.

| Fase | Situação | Observação |
|------|----------|------------|
| 0.1 a 0.6 | ✅ Feito | Backup, stack antiga desligada, webhook corrigido, credenciais do MP no `.env`. |
| 0.7 (WhatsApp da loja) | ⚠️ Parcial | Número no `.env`, sem fallback falso no app. Falta conferir visualmente (Perfil → WhatsApp). |
| 0.8 (notificação CallMeBot) | ⏳ Pendente | Depende da chave do dono. |
| 0.9 (fotos) | ❓ Não verificado | Conferir se todos os produtos têm `image_url`. |
| 0.10 (teste com dinheiro real) | ⏳ Pendente | Depende do dono. |
| Fase 1.1 a 1.4, 1.6, 1.7 | ✅ Feito | Backup diário, limites de requisição, expiração do Pix, estorno, CSP e headers, CORS e lint no CI. |
| Fase 1.5 (monitoramento) | ⚠️ Parcial | Logs com ID do pedido e `/api/health` prontos. Falta o uptime externo (`docs/MONITORAMENTO.md`). |
| Cópia do backup fora da VPS (1.1) | ⏳ Pendente | Destino ainda não definido (pergunta da seção 3). |
| Fase 2.1 (configurações da loja) | ✅ No ar (20/10) | Tabela `store_settings`: taxa de entrega, loja aberta e aviso. Aba "Loja" no painel (dono). Pedidos recusam com a loja fechada. Aviso aparece no topo do catálogo. Horários e CEPs pendem das respostas do dono. |
| Fase 2.2 (usuários do painel) | ✅ No ar (20/10) | Tabela `admin_users` (bcrypt), login por e-mail, papéis dono e atendente, revogação por versão de sessão, aba "Usuários". Dono inicial criado de `APP1_ADMIN_EMAIL`. `APP1_ADMIN_SECRET` gerada no `.env`. |
| Fase 2.3 (histórico de status) | ✅ No ar (20/10) | Tabela `order_events` gravada na mesma transação de cada mudança (cliente, Mercado Pago, sistema, usuário do painel). Botão "Histórico" no pedido. Pedidos antigos sem registros. |
| Fase 2.5 (estoque) | ✅ No ar (20/10) | `products.stock` (vazio = sem controle; os 7 produtos atuais estão assim). Reserva na criação do pedido, devolve no cancelamento e na expiração. Premissa: vale para pronta entrega e encomenda, até o dono decidir. Catálogo mostra "Esgotado" (botão desabilitado). |
| Fase 2.6 (variações por produto) | ✅ Feito (20/10, sem deploy ainda) | Tabela `product_options` (tamanhos e adicionais com preço, no painel). Carrinho envia `option_ids` e o servidor calcula o preço. Brownies receberam as opções antigas (9x9cm, Fatia grande, sem lactose +R\$3). Carrinho antigo com `size`/`lactose_free` pede para atualizar a página. |
| Fase 2.4 (pronta entrega × encomenda) | ⏸️ Pausada | Depende das respostas do dono (horários, antecedência, limite por faixa). |
| Fase 3.1 (PWA) e 3.2 (SEO) | ⚠️ Parcial (20/10, sem deploy) | Manifest com as cores da marca (`#FDEFE2`/`#412414`), `start_url` `/`, `lang` pt-BR. `robots.txt` (bloqueia `/admin`, `/api/`, `/pedido/`), `sitemap.xml`, Open Graph/Twitter e texto `<noscript>` no `index.html`. Pendente: ícones novos a partir do logo (§3) e foto do brownie na `og:image` (hoje usa o ícone 512). |
| Fase 3.3 (status para o cliente) | ⚠️ Parcial (20/10; "Avisar cliente" sem deploy) | Coluna `orders.tracking_token` (pedidos antigos ganham token ao subir a API). `GET /api/orders/:id/tracking?t=` aceita o token sem login; sem token, vale a sessão do dono, como antes. Link `/pedido/TD-XXXX?t=...` abre o acompanhamento por cima da loja. Tela de confirmação com "Copiar link de acompanhamento". Painel: botão "Avisar cliente" no card do pedido abre o wa.me com a mensagem e o link. Pendente: mensagem automática, que depende da decisão sobre a Meta API (§3). |
| Fase 3.5 (acabamento de UX) | ⚠️ Parcial (20/10, sem deploy) | Catálogo e favoritos mostram "Não foi possível carregar" com "Tentar de novo" (o fallback com produtos fixos saiu). Carrinho avisa "A loja está fechada" e desabilita "Finalizar pedido". Contraste: botão primário com texto escuro (4,8:1 no lugar de 2,9:1), "Ver carrinho" e ícone de busca sem azul-claro. Botões só com ícone têm rótulo e tooltip para leitor de tela. Esqueleto de cards no catálogo enquanto a API responde (movimento reduzido respeitado). Pendente: aviso de alergênicos (precisa do conteúdo do dono). |
| Fase 3.6 (painel com cara de produto) | ⚠️ Parcial (20/10, sem deploy) | Alerta sonoro e vibração quando entra pedido pago (checagem a cada 30 s, também fora da aba Fila). Botão "Comanda" abre a comanda para imprimir. "Exportar CSV" no Financeiro. Ajustes para celular: abas com rolagem, botões de largura total e tabelas com rolagem. Não testado num celular real. |
| Fase 3.4 (páginas legais) | ⚠️ Parcial (20/10, sem deploy) | Termos de Compra e Política de Privacidade no Perfil e no checkout. Aceite obrigatório no checkout; o pedido grava `accepted_terms_at` e a API recusa pedido sem o aceite. Vendedor vem de `APP1_SELLER_NAME` e `APP1_SELLER_DOCUMENT` no `.env`; sem eles, o texto cita "a Tri Doçuras". Pendente: o dono preencher o CNPJ ou CPF e revisar os textos com advogado, principalmente cancelamento e arrependimento. |
| Fase 4.5 (métricas) | ✅ Feito (20/10, sem deploy ainda) | Financeiro ganha pedidos criados, conversão (pagos / criados) e Pix vencido (vencidos / pagos + vencidos), pelo `created_at` do período. "Pedidos por dia" continua mostrando só os pagos, como antes. |
| Fase 4.2 (testes de integração) | ✅ Feito (20/10) | Job `integracao` no CI com Postgres 16 como serviço. Cobre reserva da última unidade com pedidos simultâneos e devolução de estoque ao cancelar. Os testes são pulados sem `DATABASE_URL`, então a suíte normal não muda. Fluxo do webhook do Mercado Pago ainda não coberto. |
| Fase 4.4 (limpeza) | ✅ Feito (20/10) | Removidos `docker-compose.yml`, `nginx/`, `scripts/issue-certs.sh` e `scripts/reload-nginx.sh` (stack antigo). `scripts/backup-tridocuras.sh` fica, porque o compose ativo o usa. Decisão sobre `apps/app2` continua aberta. |
| Fase 4.1 (migrações versionadas) | ✅ Feito (20/10, sem deploy ainda) | Runner em `api/lib/migrations.dart` com tabela `schema_migrations`. A versão 1 é o `ensureSchema` atual (idempotente). Versões repetidas são recusadas na subida. Cada migração roda na própria transação. |
| Fase 4.3 (testes de widget) | ⚠️ Parcial (20/10) | Suíte Flutter rodada no SDK (`ghcr.io/cirruslabs/flutter:stable`): análise com `--fatal-infos` e 67 testes passando. Teste de widget do estado de erro do catálogo. Golden e testes do checkout com MP mockado ficam para depois. |
| Segurança (20/10) | ✅ Feito | Pedido sem cliente (anterior ao login) deixou de ser público: `canAccessOrder` recusa, e o acompanhamento só abre com `tracking_token`. Antes, qualquer um lia esses pedidos pelo número sequencial. |
| Fase 4 (4.6) | ⏸️ Pausada | Parte da 4.4 (docs) feita em 20/10: `README.md` da raiz, `apps/app1/README.md` e `docs/`. Restante não iniciado. |
| Contas de cliente, Fases A e B | ✅ Feito | Ver [`CONTAS.md`](CONTAS.md). |
| Contas de cliente, Fases C e D | ✅ Feito (20/10, sem deploy ainda) | C.1: o card do pedido mostra "Cliente com conta · e-mail" ou "Pedido sem conta (anterior)". C.2: revisado, o JSON do painel não inclui hash de senha. D.1: cadastro exige o aceite, grava `accepted_terms_at`. D.2: `DELETE /api/customers/me` pede a senha, recusa com pedido em andamento, apaga a conta e anonimiza os pedidos. D.3 (exportação) fica opcional. |

Sobre o item 4.4: a documentação de `apps/app2` (AssistFin) ainda cita
`/opt/hosting`. Essa cópia está fora do escopo deste plano (ver topo do
arquivo), então não foi alterada.
