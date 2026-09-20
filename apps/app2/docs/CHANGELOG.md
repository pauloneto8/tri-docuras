# Changelog — AssistFin

Registro das principais evoluções do projeto (App 2).

## Unreleased

- **Datas relativas mais ricas no NLU** — `app/services/tools.py::parse_date`/`parse_user_date`; reconhece "anteontem", "depois de amanhã", "daqui a N dias"/"em N dias", "semana que vem"/"passada"/"seguinte" e dias da semana ("segunda", "próxima sexta"); corrige bug em que "anteontem"/"depois de amanhã" resolviam como "ontem"/"amanhã" por checagem de substring; data sem ano ("15/08") passa a resolver para o próximo ano se já tiver passado. `WEEKDAYS_PT` novo; `_RELATIVE_DATE_TOKEN_RE` e `is_date_only_message` atualizados em conjunto para não reabrir o bug de data isolada virar multi-lançamento
- **Correspondência aproximada de nomes (contas/cartões/categorias)** — `app/services/fuzzy_match.py` (novo, `difflib` da stdlib, sem dependência nova, cutoff 0.78, ignora acento); usado como fallback (só depois do match exato/substring falhar) em `finance.py::find_category_by_name` e em `transaction_slots.py::infer_card_name`/`infer_account_name`/`parse_account_answer`/`parse_category_answer`. Tolera erro de digitação em nome já cadastrado (ex.: "Nubanck" → "Nubank") sem pular a confirmação de escrita
- **Multi-lançamentos: tipo por cláusula e dedup por descrição** — `app/services/multi_movements.py`; mensagens com despesa e receita juntas ("gastei 50 no mercado e recebi 30 de reembolso") agora dividem corretamente por tipo em vez de assumir despesa para tudo; dedup passa a usar `(valor, descrição)` em vez de só valor, então dois itens de valores iguais e descrições diferentes não são mais descartados como duplicata. Limitação conhecida: cláusulas só são separadas por "." ou " e " (não vírgula)
- **Exemplos few-shot no prompt do agente** — `app/agent/prompt.py::SYSTEM_PROMPT`; adiciona 14 pares mensagem→JSON para as ambiguidades de maior risco já cobertas por regra em prosa (cartão vs conta, despesa vs receita, editar vs criar, transferência nova vs correção, parcelamento, pagar fatura, excluir vs listar). Mudança só de texto, mesmo prompt usado por Groq e pelo fallback Claude
- **Inteligência proativa (opcional, desligada por padrão)** — `app/agent/claude.py` (2º modelo, Claude Haiku, só leitura/explicação); `app/services/insights.py` gera e valida insight mensal a partir de `get_summary`/`get_budget_status`; tabela `agent_insights` (migração `020`); `python -m app.scripts.generate_insights` para cron diário; exibido nas boas-vindas do chat. `ENABLE_AI_INSIGHTS`/`ANTHROPIC_API_KEY`. Ver `.cursor/plans/agente-inteligencia-proativa.md`
- **Fallback de NLU via Claude (opcional, desligado por padrão)** — `_resolve_intent` (`runner.py`) tenta Claude Haiku (`call_claude_tool_call`, mesmo `SYSTEM_PROMPT` de tool-calling do Groq) como 3º nível, só quando Groq **e** `try_rule_based_parse` falham; resultado passa pelo funil normal de confirmação. `source=claude-fallback` em `conversation_messages`. `ENABLE_AI_NLU_FALLBACK`/`ANTHROPIC_API_KEY`
- **Memória de personalização (sem LLM, sempre ativa)** — `app/services/agent_preferences.py`; após 3 lançamentos manuais seguidos com a mesma descrição normalizada, categoria e/ou forma de pagamento, o agente **pergunta** se deve lembrar (nunca salva sozinho); "sim" grava em `agent_description_preferences` (migração `021`) e passa a pré-preencher categoria/cartão/conta nas próximas vezes, sem pular a confirmação de escrita. Ver `.cursor/plans/agente-inteligencia-proativa.md` (Fase 4)
- **Orquestrador multi-etapas via Claude (opcional, desligado por padrão)** — `app/agent/orchestrator.py`; pedidos amplos ("revise meus gastos e sugira cortes", detectados por `looks_like_broad_request`) desviam do roteamento de intenção única para o Tool Runner do Claude Sonnet (SDK oficial `anthropic`, novo em `requirements.txt`), que só enxerga as ferramentas de leitura (`list_transactions`, `get_summary`, `get_budget_status`, `list_categories`, `list_invoices`) — nunca escrita. Mesma validação anti-alucinação da Fase 2 (descarta resposta que cite valor não devolvido por nenhuma ferramenta). `source=claude-orchestrator` em `conversation_messages`. `ENABLE_AI_ORCHESTRATOR`/`ANTHROPIC_API_KEY`/`ANTHROPIC_MODEL_REASONING`. Ver `.cursor/plans/agente-inteligencia-proativa.md` (Fase 5)
- **Wizard cartão vs conta** — slot `payment_source` quando ambíguo; inferência `card_name` em “lançado no cartão”; confirmação mostra **Cartão:**; `resolve_movement_accounts` usa conta de liquidação quando apelido do cartão = nome da conta
- **Filtros em Movimentos** — conta, cartão, **categoria** e tipo; período diária/semanal/mensal; estado memorizado na sessão HTTP até `?clear=1` (Limpar → padrão mês atual sem restrições)
- **Importação de extrato** — OFX/QFX, CSV e PDF (texto) no mesmo fluxo de revisão (cartão e conta); parser compartilhado `statement_parse.py`; upload até **10 MB**
- **PDF** — `pdfplumber`; ignora coluna/saldo final da linha; sinal negativo (Unicode, `75,50-`, célula separada); PDFs escaneados não suportados
- **Flash CSV** — `flash_extrato_*.csv` (TAB, `-R$` com NBSP, ignora saldo); débitos/créditos pelo sinal
- **CSV genérico** — detecta delimitador, preâmbulo e colunas sem nomes fixos
- **OFX cartão** — `/accounts/cards/{id}/ofx`: criar/conciliar/pagar fatura; staging `ofx_import_*` + `transactions.ofx_fitid`
- **OFX conta** — `/accounts/{id}/ofx` (débito=despesa, crédito=receita, `actual`); migração `019` (`account_id` no lote)
- **OFX revisão** — nada ignorado sem confirmação; fatura de vínculo; categoria memorizada por descrição
- **Excluir fatura** — remove fatura + movimentos do cartão; pagamento bancário (se pago) permanece
- **Admin** — backup/restauração PostgreSQL em `/admin`; volume `app2_backups`
- **Restore** — reset do schema `public` + `alembic upgrade head` pós-restore
- **LLM** — somente Groq; fallback de regras se a API falhar
- **Wizard / edição** — slots só perguntam o que faltar; editar tipo Despesa↔Receita; escopo de parcela `this`/`subsequent`
- **Categorias no assistente** — `list_categories` / `update_category` / `delete_category`; lote `names`
- **Dashboard** — previsto × realizado por categoria
- Suite: **pytest** no container (`tests/test_statement_parse.py`, filtros em `test_summary.py`, OFX conta/cartão)

## 2026-09-04 — CRUD nas telas, filtros, cartões aninhados e resumo no chat

- **CRUD na UI** — Movimentos, Contas, Cartões e Orçamentos em páginas separadas (lista + `/new` + `/{id}/edit` + delete/desativar); formulários laterais removidos das listagens
- **Movimentos** — filtro de período (diária/semanal/mensal; padrão = mês atual); extrato omite `transfer_in` (par só pela saída)
- **Dashboard** — indicadores **Por categoria** (despesas e receitas do período com % e barra); `expenses_by_category` / `income_by_category` em `get_summary()`
- **Cartões** — UI hierárquica expansível: cartão → faturas → movimentos (`cards_with_nested_invoices`); lista solta de faturas removida
- **Chat** — após `register_expense` / `register_income` (e ao realizar previsto), anexa resumo da **fatura** (cartão) ou da **conta** (bancária) via `enrich_register_result` / `context_summary`
- Helpers: `format_period_label`, `account_context_summary`, `invoice_context_summary`, `list_invoice_movements`
- Testes: `test_summary_category_breakdown`, `test_cards_with_nested_invoices_*`, `test_register_expense_chat_includes_*`, format em `test_tools.py`

## 2026-09-02 — Visual completo do chat

- Avatares: assistente (ícone) à esquerda, inicial do usuário à direita
- Balões assimétricos (`rounded-2xl` + canto cortado); chips e Confirmar/Cancelar **fora** do balão
- Filtro Jinja `chat_md` (`app/chat_format.py`): `*negrito*` / `**negrito**`, listas `- `, HTML escapado
- Welcome com chips clicáveis; cabeçalho do painel com avatar
- Testes: `tests/test_chat_format.py`
- Suite: **244** testes

## 2026-09-02 — Parcelamento: total vs parcela, parcela inicial e datas

- Parcelamento — valor: pergunta se o valor informado é o **total da compra** ou o **valor de cada parcela** (`installment_amount_basis`; wizard + formulário Movimentos)
- Parcelamento — parcela inicial: pergunta qual parcela está sendo lançada (`installment_start_index`); gera somente da parcela informada até a última (ex.: 180/360 → parcelas 180…360)
- Parcelamento — datas no wizard: competência e vencimento da **parcela atual** perguntados após N/intervalo/índice; cronograma ancora no `due_date`; em realizado, `payment_date` **não** sobrescreve competência/vencimento
- Parcelamento — inferência: datas relativas da mensagem inicial (`ontem`, `hoje`) **não** preenchem slots de parcelamento; ao escolher *parcelado*, datas genéricas anteriores são limpas
- Realizado no wizard: pergunta `payment_mode` (único/fixo/parcelado) **antes** de `payment_date` quando ainda não há modo definido
- Confirmação de parcelamento: exibe competência, vencimento e data de realização separadamente

## 2026-09-02 — Corrigir transferência (`update_transfer`)

- Nova ferramenta `update_transfer` para alterar origem, destino, valor ou data de um par já lançado
- Heurística e prompt: "corrija a transferência…" **não** usa `update_transaction` nem cria outra transferência
- Testes: `tests/test_update_transfer.py`

## 2026-09-01 — Cartões como entidade separada e CRUD no assistente

- Nova tabela `credit_cards` — cartão **não** é mais conta bancária (`account_type=cartao` legado migrado e desativado; migração `016`)
- `CardInvoice` referencia `card_id`; `Transaction` aceita `card_id` opcional + `account_id` opcional (pelo menos um obrigatório)
- Compras no cartão não alteram saldo bancário; pagamento de fatura = despesa na conta de débito (não transferência para “conta-cartão”)
- UI: menu **Cartões** → `/accounts/cards`; formulário próprio com conta de liquidação obrigatória
- Movimentos: campos **Cartão** e **Conta** independentes
- Assistente:
  - `create_card` — wizard (`card_wizard.py`): apelido, fechamento, vencimento, limite, conta de liquidação
  - `update_card` — editar apelido, instituição, limite, fechamento, vencimento, liquidação (confirmação obrigatória)
  - `delete_card` — exclusão lógica (`is_active=false`; histórico preservado)
  - `list_invoices`, `pay_invoice` — consultar e pagar faturas
- Testes: `test_credit_cards.py`, `test_card_wizard.py`, `test_update_card.py`, `test_runner_update_card.py`
- Suite: **222** testes

## 2026-09-01 — Cartões de crédito e faturas (inicial)

- Contas `cartao` com limite, dia de fechamento e vencimento (substituídas pela entidade `credit_cards` na revisão `016`)
- Tabela `card_invoices` e `transactions.invoice_id` (migração `015`)
- Compras no cartão atribuídas à fatura do ciclo
- UI em `/accounts`: fatura atual, limite disponível, **Pagar fatura**
- Skill `assistfin-credit-cards`

## 2026-08-31 — Lançamentos parcelados

- Despesas e receitas **parceladas** em N vezes iguais (intervalo mensal, semanal ou quinzenal)
- Nova tabela `installment_plans` e campos `installment_plan_id` / `installment_index` em transações (migração `014`)
- Valor informado = total; `split_cents()` divide em parcelas (resto de centavos na última)
- Todas as N ocorrências geradas na criação; futuras como `planned`; 1ª pode ser `actual`
- Formulário em Movimentos: checkbox **Parcelado**, número de parcelas e intervalo (mutuamente exclusivo com fixo)
- Selo `3/12 · mensal` na lista **A realizar**; ação **Cancelar parcelas** (`POST /transactions/installments/{id}/stop`)
- Wizard do assistente: slot `payment_mode` (único / fixo / parcelado), depois parcelas e intervalo
- Skill de projeto: `.cursor/skills/assistfin-installments/SKILL.md`
- Testes em `tests/test_installments.py`
- Suite: **202** testes

## 2026-08-31 — Lançamentos fixos (recorrência)

- Despesas e receitas **fixas** com frequência diária, semanal ou mensal
- Nova tabela `recurring_rules` e campo `recurrence_id` em transações (migração `013`)
- Geração automática de previstos até `min(data_término, hoje + 3 meses)`; horizonte reabastecido ao acessar Movimentos/Dashboard e após realizar ocorrência
- Formulário em Movimentos: checkbox **Lançamento fixo**, frequência e término opcional
- Selo `Fixo · mensal/semanal/diária` na lista **A realizar**; ação **Encerrar série** (`POST /transactions/recurring/{id}/stop`)
- Wizard do assistente: pergunta se repete, frequência e data de término (após datas, antes do valor)
- Correção: responder **não** no slot de recorrência não cancela mais o wizard
- Testes em `tests/test_recurrence.py`
- Suite: **194** testes

## 2026-08-31 — Realizar previsto com escolha de conta

- Ao realizar uma previsão, pergunta se será na **mesma conta** do previsto ou em **outra conta**
- UI em Movimentos: radio mesma/outra conta no formulário **Realizar**
- Wizard `realize_planned_slots.py` no assistente (pagamento → mesma conta? → conta)
- `realize_planned()` atualiza `planned.account_id` quando a conta informada difere
- Testes em `tests/test_realize_planned_wizard.py` e `tests/test_planned_transactions.py`

## 2026-08-31 — Correção: data no wizard vs multi-lançamentos

- Ao responder **vencimento** ou **competência** com data (`10/08/2026`, `hoje`, `agosto`), o assistente preenchia o slot correto em vez de criar vários lançamentos
- **Causa:** `parse_multi_movements()` interpretava `10/08/2026` como três valores (`10`, `08`, `2026`) e abria o fluxo multi
- **Correções:**
  - `is_date_only_message()` em `tools.py` — distingue data isolada de narrativa com despesas (ex.: "Ontem tive despesas de 54...")
  - Wizard de transação processado **antes** de `try_begin_from_message` quando o próximo slot é data (`DATE_SLOTS`)
  - `try_begin_from_message` ignora multi-lançamento com wizard ativo em slot de data, conta ou categoria
- Testes: `test_date_only_not_multi`, `test_runner_due_date_does_not_spawn_multi_expenses` em `tests/test_multi_movements.py`
- Suite: **183** testes

## 2026-08 — Tela de Movimentos (previstos vs realizados)

- Página `/transactions` dividida em **A realizar** (previstos pendentes) e **Extrato** (somente realizados)
- Previstos já liquidados deixam de aparecer na lista (o par previsto/realizado permanece no dashboard)
- Uma data principal por linha: vencimento no previsto, pagamento no realizado
- Um selo de status por linha; realizados de previsto exibem “de previsto” em vez de duplicar badges
- `ListTransactionsInput` com filtro `status` (`actual` | `planned` | `all`)
- Formulário manual alinhado ao wizard: realizado pede só data da realização; previsto pede competência e vencimento
- Ação **Realizar** simplificada: pagamento obrigatório; valor e descrição opcionais
- Teste `test_list_transactions_filters_by_status` em `tests/test_planned_transactions.py`

## 2026-08 — Competência, vencimento e datas no assistente

- Campos `competence_date`, `due_date`, `payment_date` em transações
- Migração `012_transaction_competence_dates` (check: previsto sem pagamento, realizado com pagamento)
- Orçamentos passam a usar **competência**; saldos usam data de **pagamento** (caixa)
- Wizard de lançamento pergunta datas conforme o status:
  - **Previsão** → competência e vencimento
  - **Realizado** → data da realização (replicada em competência e vencimento)
- Chips de data: Hoje, Ontem, Amanhã
- `parse_user_date()` para formatos relativos e absolutos (BR, ISO, mês por extenso)
- Confirmação exibe competência/vencimento (previsto) ou data da realização (actual)

## 2026-08 — Previsto vs realizado

- Campo `status` (`planned` / `actual`) e `source_planned_id`
- Ferramenta `realize_planned` no assistente
- Dashboard com previstos, pendentes e projeção de saldo
- Migração `011_planned_transactions`

## 2026-08 — Transferências e movimentos

- Tipos `transfer_out` / `transfer_in` com par vinculado (`transfer_group_id`)
- Transferências afetam saldos das contas, **não** receitas/despesas do período
- Ferramenta `register_transfer` no assistente + formulário em Movimentos
- Exclusão de uma perna remove o par inteiro
- Migração `010_transaction_transfers`

## 2026-08 — Dashboard e períodos

- Visões diária, semanal e mensal com navegação por data
- Cards: Receitas, Despesas, Resultado do período, Saldo anterior, Resultado final
- Saldos por conta respeitam o fim do período selecionado
- Removido card "Saldo total" do dashboard (mantido na API)
- Formatação BRL (`1.234,56`)

## 2026-08 — Saldo inicial com data

- Campo `opening_balance_date` em contas
- Saldo inicial só conta a partir da data declarada
- Assistente treinado para `update_account` com data do saldo inicial
- Migração `008_account_opening_balance_date`

## 2026-08 — Assistente

- Chips clicáveis para respostas rápidas no chat
- Cancelar limpa estado no servidor (wizards, pendências)
- `list_categories` — listar categorias cadastradas
- Normalização ortográfica de nomes de categoria (`correct_category_name`)
- Correção de memória ao cancelar wizard de transação
- Migração `009_normalize_category_names`

## 2026-08 — UI

- Menu "Extrato" renomeado para **Movimentos**
- Lista de movimentos com tipo (despesa, receita, transferência)
- Reorganização da tela Movimentos: seções **A realizar** e **Extrato** (ver entrada acima)

## Anterior

- Multiusuário com aprovação admin
- Onboarding obrigatório (primeira conta)
- Wizards de conta, categoria e transação
- Groq + Ollama (fallback)
- Edição/exclusão de lançamentos e contas
- Múltiplos lançamentos em uma mensagem
- Logs de conversa (`conversation_messages`)
- CSRF, rate limit, CSP, TrustedHost
