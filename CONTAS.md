# Tri Doçuras — contas de cliente e perfil

Gravado em 20/10/2026. Plano para outro agente implementar. Não está no escopo
do `PLANO.md` original, e deve ser executado **depois da Fase 0** (a loja precisa
vender antes de exigir cadastro).

Decisões do dono (20/10):

| Tema | Decisão |
|------|---------|
| Login | **E-mail e senha**, sem custo recorrente. (WhatsApp com código fica para depois, se valer o custo de provedor.) |
| Compra sem conta | **Não existe.** Todo pedido fica ligado a um cliente. |
| Como executar | **Plano escrito** (este arquivo). Quem implementa revisa antes e segue as fases. |

---

## 0. Estado atual (o que não serve para contas)

- **Nenhum cliente no servidor.** A tabela `orders` guarda `customer_name` e
  `whatsapp` como texto solto; não há `customer_id`.
- **Histórico de pedidos e favoritos ficam só no celular:**
  `apps/app1/frontend/lib/orders/order_history_controller.dart` e
  `apps/app1/frontend/lib/favorites/favorites_controller.dart` usam
  `SharedPreferences`. Trocar de celular ou limpar o navegador apaga tudo.
- **Checkout pede nome, WhatsApp e endereço a cada pedido**
  (`lib/checkout/checkout_draft.dart`, `order_payload.dart`). Com conta, esses
  dados vêm do perfil.
- **Rastreamento por ID sequencial** (`GET /api/orders/{id}/tracking`), público.
  Com contas, o rastreamento passa a exigir que o pedido seja do cliente logado.
  (O item 3.3 do `PLANO.md` previa um token por pedido; **com contas, o token
  deixa de ser necessário** para o cliente logado. Manter o link de WhatsApp
  para quem não logar é decisão a tomar na Fase 3.)
- **Painel admin** tem login próprio (senha única). Não é afetado: contas de
  cliente e o painel usam sistemas de sessão separados.

---

## 1. Regras para quem executar

- Siga as regras da seção 0 do `PLANO.md`: deploy só pelo
  `docker-compose.tridocuras.yml`, `Env.get` para ler variáveis, schema por
  `ensureSchema` idempotente (`ADD COLUMN IF NOT EXISTS` / `CREATE TABLE IF NOT EXISTS`).
- **Nenhum segredo** em código, log ou commit. Senhas só como hash.
- Cada item novo vem com teste. CI verde antes do deploy.
- Commits por item, padrão `tipo(app1): descrição`, com o trailer de coautoria.
- **Não dê push nem deploy** sem o dono autorizar.
- Em dúvida de produto (texto, regra de negócio, dado a pedir), **pare e pergunte**.

---

## 2. Fases

### Fase A — Backend de contas · ~3 dias

| # | Item | Pronto quando |
|---|------|---------------|
| A.1 | **Tabela `customers`:** `id`, `email` (único, normalizado em minúsculas), `password_hash` (**argon2id** ou bcrypt), `name`, `whatsapp`, `created_at`, `email_verified_at`, `disabled_at`. | Criada por `ensureSchema`; `email` único é garantido pelo banco. |
| A.2 | **Hash de senha** em módulo próprio (`lib/customer_auth.dart`), com testes: hash não é reversível, senha errada falha, hash diferente para a mesma senha (sal). | Testes verdes. Nenhuma senha em log. |
| A.3 | **Cadastro** `POST /api/customers`: e-mail, senha (mínimo 8 caracteres), nome, WhatsApp. Responde 201 sem devolver o hash. E-mail duplicado → 409 com mensagem genérica (não confirmar se o e-mail existe em outras respostas). | Testes: duplicado, senha curta, e-mail inválido. |
| A.4 | **Login** `POST /api/customers/session`: e-mail + senha, devolve token. **Rate limit** igual ao do painel (5 tentativas a cada 15 min por IP, `rate_limiter.dart`). Mensagem única para "e-mail não existe" e "senha errada". | Testes com 429 e mensagem genérica. |
| A.5 | **Token de sessão do cliente:** HMAC com chave própria `APP1_CUSTOMER_SECRET` (**não** reutilizar a senha de admin nem a do Mercado Pago). Expira em 30 dias. Ver como o `admin_auth.dart` faz hoje, mas com chave separada. | Teste: token de admin não serve para cliente e vice-versa. |
| A.6 | **Perfil** `GET` e `PUT /api/customers/me`: nome, WhatsApp, endereços salvos (lista). Trocar senha exige a senha atual. | Testes de autorização: sem token → 401; cliente A não lê dados do cliente B. |
| A.7 | **Recuperação de senha:** `POST /api/customers/password-reset` gera token de uso único, válido 1 h, enviado por e-mail. Resposta sempre igual, exista o e-mail ou não. | Requer provedor de e-mail (ver seção 3). Sem ele, este item fica pendente, mas A.1–A.6 não dependem dele. |
| A.8 | **Vincular pedidos:** `orders.customer_id` (nullable só para pedidos antigos). `createOrder` exige token e grava `customer_id`. Pedido sem token → 401. | Teste: pedido sem token é recusado; pedido com token grava o cliente. |
| A.9 | **Histórico no servidor:** `GET /api/customers/me/orders` (só os próprios pedidos, mais recentes primeiro). | Teste: não vaza pedido de outro cliente. |
| A.10 | **Rastreamento autenticado:** `GET /api/orders/{id}/tracking` passa a exigir token e que o pedido seja do cliente. A rota sem login deixa de existir (ou passa a responder 404 para pedidos com `customer_id`). | Teste: cliente A não rastreia pedido do cliente B. |
| A.11 | **Pedidos antigos sem conta:** continuam no banco com `customer_id = NULL` e aparecem no painel normalmente. Não são vinculados automaticamente (WhatsApp não é prova de identidade). | Migração idempotente, sem apagar nada. |

### Fase B — Front: cadastro, login e perfil · ~4 dias

| # | Item | Pronto quando |
|---|------|---------------|
| B.1 | **Tela de cadastro e login** (e-mail, senha, nome, WhatsApp). Mensagens de erro em português, sem detalhe técnico. | Revisão manual no celular (viewport de 390 px, sem zoom). |
| B.2 | **Sessão persistida** no celular (`SharedPreferences` só para o token; nada de pedido ou dado pessoal). Token expirado ou recusado (401) leva para o login sem perder o carrinho. | Teste de widget: 401 redireciona e preserva o carrinho. |
| B.3 | **Checkout exige login:** quem não está logado vê "Entrar ou criar conta" antes de pagar. Carrinho sobrevive ao login. Nome, WhatsApp e endereço vêm do perfil e podem ser editados no checkout. | Teste: sem login não há botão "Gerar Pix". |
| B.4 | **Aba Perfil:** dados pessoais, endereços salvos, trocar senha, sair. | Teste: as alterações chegam ao servidor. |
| B.5 | **Histórico e favoritos do servidor:** a aba Pedidos lê `GET /api/customers/me/orders`. Favoritos passam a ser salvos no servidor (nova tabela `customer_favorites`), com migração do que estiver no `SharedPreferences` do aparelho. | Teste: favorito sobrevive a trocar de celular. |
| B.6 | **Recuperação de senha no app** (depende de A.7). | Fluxo ponta a ponta com e-mail real. |

### Fase C — Painel e operação · ~1 dia

| # | Item | Pronto quando |
|---|------|---------------|
| C.1 | No detalhe do pedido, mostrar se o cliente tem conta e o e-mail dele (só para o painel). | Painel mostra "Cliente com conta" ou "Pedido sem conta (anterior)". |
| C.2 | Não criar campo de senha nem de "ver senha" no painel. O atendente não vê nem altera senha de cliente. | Revisão de código: nenhum endpoint admin devolve hash ou senha. |

### Fase D — Dados pessoais (LGPD) · junto com o item 3.4 do PLANO.md

| # | Item | Pronto quando |
|---|------|---------------|
| D.1 | Consentimento no cadastro com link para a Política de Privacidade (item 3.4). Grava `accepted_terms_at` no cliente. | Cadastro não passa sem o aceite. |
| D.2 | **Excluir conta:** `DELETE /api/customers/me` apaga os dados pessoais e mantém os pedidos com `customer_id = NULL` e nome anonimizado (o financeiro precisa dos valores). | Teste: depois de excluir, o login falha e os pedidos não mostram nome. |
| D.3 | Exportação dos dados do próprio cliente (JSON), se o dono quiser atender pedidos de LGPD pelo app. | Opcional; decidir na revisão. |

---

## 3. Dependências e perguntas em aberto

| Pergunta | Quem responde | Impacto |
|----------|---------------|---------|
| **Provedor de e-mail** para recuperação de senha (Resend, SendGrid, Amazon SES, ou o próprio SMTP do domínio)? | Dono | Bloqueia A.7 e B.6. Sem ele, o cliente que esquece a senha precisa falar com a loja, e o painel precisa de um botão "redefinir senha" para o atendente. |
| O cliente pode **trocar o e-mail** da conta? Se sim, exige confirmação no e-mail novo. | Dono | Escopo de A.6. |
| Quantos **endereços** salvos por cliente? Sugestão: até 5. | Dono | Escopo de A.6. |
| Contas de **funcionários** também usam este login, ou só o painel (seção 2.2 do PLANO.md)? | Dono | Recomendado: separados. |
| O link de rastreamento enviado por WhatsApp (3.3) continua existindo para quem não tem conta? | Dono | Se não, o item 3.3 é simplificado. |

---

## 4. Critérios gerais de aceite do projeto

- Um cliente novo cria conta, faz um pedido, paga com Pix e vê o pedido na aba
  Pedidos **em outro celular**, logado com a mesma conta.
- Sem login, a API recusa criar pedido e rastrear pedido (401).
- Nenhum endpoint devolve senha ou hash. Nenhum log contém senha ou token.
- A suíte da API e o `dart analyze --fatal-warnings` passam no CI.
