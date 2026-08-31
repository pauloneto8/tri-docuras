# Changelog — AssistFin

Registro das principais evoluções do projeto (App 2).

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
