# Changelog — AssistFin

Registro das principais evoluções do projeto (App 2).

## Unreleased

- Dashboard: seção **Cartões e faturas** (total a pagar, vencimento no período, status, limite disponível). Dados em `get_summary()["card_invoices"]` via `invoice_dashboard()`.
- Testes: `test_summary_includes_card_invoices`; suite **246**.

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
