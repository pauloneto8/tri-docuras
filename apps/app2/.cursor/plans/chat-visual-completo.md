# Plano pendente: visual completo do chat

**Status:** implementado (2026-09-02)  
**Workspace:** `/opt/hosting/apps/app2`  
**Origem:** pedido do usuário — “os chats estão com as mensagens mal formatadas. Melhor os textos, balões, ícones, chips e os avatares.” Escopo escolhido: **visual completo**.  
**Cópia Cursor:** `/root/.cursor/plans/chat_visual_completo_f5ae157b.plan.md`

Antes de editar: `move_agent_to_root` → `/opt/hosting/apps/app2`.  
Ler: `.cursor/skills/assistfin-ai-agent/SKILL.md` e `.cursor/skills/assistfin-implementation/SKILL.md`.  
Responder em **português**.

---

## Objetivo

Reformar só a **apresentação** do chat flutuante. A lógica do agente (runner, wizards, tools, HTMX targets/swaps) **não muda**.

Hoje:

- `{{ agent_message }}` com `whitespace-pre-line` — `*negrito*` e `**negrito**` das perguntas do wizard aparecem literais.
- Chips e Confirmar/Cancelar ficam **dentro** do balão.
- Sem avatares; balões `rounded-lg` iguais nos quatro cantos.
- Chip de sugestão (`rounded-full`) ≠ botões de confirmação (`rounded`).

---

## Fora de escopo

- Não alterar `runner.py`, wizards, `agent_suggestions.py` (lista de chips), intents, LLM.
- Não encurtar `SLOT_QUESTIONS` / `QUESTIONS` (testes checam palavras-chave; o filtro `chat_md` resolve o markdown).
- Sem biblioteca de markdown (mistune, markdown2, etc.).
- Sem mudar CSP além do necessário (continuar SVG inline / Tailwind CDN).

---

## Arquivos a alterar

| Arquivo | O quê |
|---------|--------|
| `app/templating.py` **ou** `app/main.py` | Filtro Jinja `chat_md` (preferir módulo pequeno `app/chat_format.py` + registro em `main.py`) |
| `app/main.py` | `env.filters["chat_md"] = chat_md` ao lado de `local_datetime` |
| `app/templates/partials/agent_response.html` | Layout usuário + assistente |
| `app/templates/partials/agent_assistant_message.html` | Só assistente (welcome HTMX) |
| `app/templates/partials/agent_suggestions.html` | Chips fora do balão; Cancelar distinto |
| `app/templates/partials/agent_widget.html` | Welcome, cabeçalho, enviar, erros |
| `app/templates/base.html` | CSS pontual (listas no balão, avatar) |
| `app/routers/pages.py` | Incluir `"user": user` em **todos** os `TemplateResponse` de `/agent/chat` e `/agent/welcome` |
| `tests/test_chat_format.py` | Novo — filtro `chat_md` |
| `docs/CHANGELOG.md` | Uma linha na seção Unreleased |

Criar partial reutilizável se ajudar a não duplicar avatar:

- `app/templates/partials/agent_avatar.html` — `role` = `assistant` \| `user`

---

## Layout alvo

```
Assistente (esquerda):
  [avatar 32px] [balão slate rounded-2xl rounded-bl-md]
                [chips wrap, fora do balão]

Usuário (direita):
                [balão emerald rounded-2xl rounded-br-md] [avatar inicial]
```

Classes sugeridas (Tailwind):

- Linha: `flex items-end gap-2`
- Assistente: `justify-start`; usuário: `justify-end`
- Avatar: `w-8 h-8 shrink-0 rounded-full flex items-center justify-center text-xs font-semibold`
  - Assistente: `bg-emerald-600 text-white` + SVG robô/chat (mesmo traço do FAB)
  - Usuário: igual à sidebar — `bg-emerald-600/30 border border-emerald-700 text-emerald-300` + `user.name[0]|upper`
- Balão: `px-3.5 py-2.5 max-w-[85%] text-sm leading-relaxed break-words`
  - Assistente: `bg-slate-800 border border-slate-700 text-slate-100`
  - Usuário: `bg-emerald-900/50 border border-emerald-800 text-emerald-50`
- Coluna do assistente: `flex flex-col items-start gap-2 min-w-0` (balão + chips)
- Manter wrappers HTMX: `agent-exchange`, `agent-assistant-bubble`, `data-refresh-page`, `data-keep-chat-open`

### HTMX — não quebrar

`agent_suggestions.html` hoje:

- `hx-target="{{ chip_target|default('closest .agent-exchange') }}"`
- `hx-swap="{{ chip_swap|default('outerHTML') }}"`
- Welcome/assistente: `chip_target = "#agent-chat-log"`, `chip_swap = "beforeend"`

Confirmação continua:

- `hx-target="closest .agent-exchange"`
- `hx-swap="outerHTML"`
- `name="confirmed"` / `pending_action` / `message` iguais

JS em `agent_widget.html` (`htmx:afterSwap`, `data-refresh-page`, `#agent-welcome`) permanece.

`pages.py` precisa passar `user` porque o parcial HTMX **não** herda o contexto de `base.html`.

---

## Filtro `chat_md`

Módulo `app/chat_format.py`:

1. Entrada `None` / `""` → `""`
2. `html.escape(text)` primeiro
3. `**...**` → `<strong>...</strong>` (não guloso)
4. `*...*` restante → `<strong>...</strong>` (o app usa * e ** como ênfase, não itálico)
5. Blocos de linhas que (após escape) começam com `- ` → `<ul class="chat-md-list">` + `<li>`
6. Outras quebras: `\n\n` → parágrafo; `\n` → `<br>`
7. Retornar `markupsafe.Markup(...)` — **nunca** `|safe` no template em texto cru

Template do assistente: `{{ agent_message | chat_md }}`  
Template do usuário: `{{ user_message }}` (escape padrão Jinja)

Não aplicar `chat_md` em `user_message`.

### Testes (`tests/test_chat_format.py`)

- `"<script>"` não vira tag
- `"Responda com *despesa* ou *receita*."` contém `<strong>despesa</strong>`
- `"**realizado**"` → strong
- `"Últimas:\n- a\n- b"` → `<ul>` com dois `<li>`
- `"preço * 2"` (asterisco isolado / sem fechar) não explode; não inventar strong

---

## Confirmação estruturada

Quando `needs_confirmation` e `pending_action` (dict com `tool` + `arguments`):

No balão:

1. Primeira linha da mensagem (até `\n`) como título, via `chat_md`
2. Mini `dl` com campos presentes em `pending_action.arguments`:
   - `description` → Descrição
   - `amount` → Valor (prefixar `R$` se ainda não tiver)
   - `account_name` / `from_account` / `to_account` / `card`
   - `category_name`
   - `payment_date` / `transaction_date` / `competence_date` / `due_date`
   - `account_type` / `institution` / `name` (cadastro de conta/cartão)

Se `pending_action` ausente, cair no `chat_md` da mensagem inteira.

Botões **fora** do balão, na faixa de chips:

- Confirmar: `rounded-full bg-emerald-600 hover:bg-emerald-500` + ícone check + texto
- Cancelar: mesmo visual do chip Cancelar (rose/slate + X)

Manter os `<form>` HTMX atuais (hidden inputs iguais).

---

## Chips (`agent_suggestions.html`)

- Container: `mt-0 flex flex-wrap gap-1.5` **irmão** do balão, não filho
- Chip padrão: `rounded-full border border-slate-600 bg-slate-800 hover:bg-emerald-700/80 hover:border-emerald-600 px-3 py-1 text-xs`
- Chip `Cancelar`: `border-rose-800/80 bg-rose-950/40 text-rose-200 hover:bg-rose-900/60` + SVG X
- Texto: `max-w-[11rem] truncate` no botão; `title="{{ chip }}"`
- Forms continuam `inline` / `class="inline"`

---

## Widget / chrome

**Cabeçalho:** avatar assistente 32px + “Assistente” / “AssistFin com IA”

**Welcome (`#agent-welcome`):** mesma linha avatar+balão. Texto curto: “Olá! Posso ajudar com:”. Exemplos viram chips que postam `/agent/chat` (`hx-target="#agent-chat-log"` `hx-swap="beforeend"`), reusando `agent_suggestions.html` com `suggestions` fixas:

- `gastei 45 no mercado ontem`
- `resumo do mês`
- `últimas despesas`
- `status dos orçamentos`
- `cadastrar uma conta do Nubank`
- `cadastrar categoria Pet de despesa`

Remover o `<ul>` atual. O JS que faz `$('#agent-welcome').remove()` após o primeiro swap **continua válido**.

**Enviar:** botão ícone (seta/avião), `aria-label="Enviar"`, `title="Enviar"`.

**Erro JS** (`showAgentError`): mesma linguagem visual (balão rose), sem avatar obrigatório.

**CSS em `base.html`** (mínimo):

```css
.chat-md-list { list-style: disc; padding-left: 1.1rem; margin: 0.35rem 0; }
.chat-md-list li { margin: 0.1rem 0; }
.chat-bubble strong { font-weight: 600; color: inherit; }
```

---

## Verificação

```bash
cd /opt/hosting
docker compose build app2
docker compose up -d app2
docker compose exec -T app2 python -m pytest -q
```

Browser (obrigatório — mudança de UI):

1. Abrir o FAB
2. Welcome: avatar, balão, chips de exemplo
3. Clicar um chip de wizard (ex. cadastrar conta) — negrito visível, chips **abaixo** do balão, Cancelar distinto
4. Fluxo até Confirmar — resumo em linhas, botões fora do balão
5. Mensagem do usuário à direita com inicial
6. Não regressar: swap HTMX, “Pensando…”, refresh da página após gravar com chat aberto

---

## Critério de pronto

- Asteriscos de wizard viram negrito, não texto cru
- Listas (`format_tool_result` com `- item`) viram `<ul>`
- Avatares nas duas pontas
- Chips e confirmação fora do balão
- `user` presente nos parciais HTMX
- pytest verde no container
- Fluxo conferido no browser
