# Matriz de testes do agente

## Cenários

| Mensagem do usuário | Esperado | Teste |
|---------------------|----------|-------|
| "Quais a conta bancária?" | `list_accounts` | `test_intents.py` |
| "Liste minhas categorias" | `list_categories` | `test_list_categories.py` |
| "transferir 100 da Nubank para Carteira" | `register_transfer` | `test_transfers.py` |
| "Corrija a transferência de 594… de Flash para Mercado Pago" | `update_transfer` | `test_update_transfer.py` |
| "Cadastrar nova conta" no wizard tx | wizard conta | `test_runner_wizard_escape.py` |
| "Liste minhas contas" no wizard conta | escape + list | `test_list_accounts.py` |
| "resumo do mês" no wizard tx | escape + summary | `test_runner_wizard_escape.py` |
| Cancelar no meio do wizard | estado limpo | `test_agent_cancel.py` |
| "criar categoria consumo" | nome "Consumo" | `test_category_wizard.py` |
| "despesa" → "previsto" | pergunta competência | `test_transaction_wizard.py` |
| "despesa" → "realizado" | pergunta data da realização | `test_transaction_wizard.py` |
| previsto: competência + vencimento | `competence_date` + `due_date` | `test_transaction_slots.py` |
| previsto: vencimento `10/08/2026` | um slot preenchido, sem multi | `test_multi_movements.py` |
| após datas: "não" em fixo | continua wizard (não cancela) | `test_transaction_wizard.py` |
| aluguel mensal fixo | `frequency=monthly`, previstos no horizonte | `test_recurrence.py` |
| encerrar série | remove previstos pendentes | `test_recurrence.py` |
| "cadastrar cartão Nubank" | `create_card` + wizard | `test_card_wizard.py` |
| "altere vencimento do cartão Nubank para dia 20" | `update_card` | `test_update_card.py` |
| "excluir cartão Nubank" | `delete_card` | `test_update_card.py` |
| realizar previsto em outra conta | wizard pergunta mesma conta → conta | `test_realize_planned_wizard.py` |
| "Ontem despesas 54... e 30 recarga" | fluxo multi-lançamento | `test_multi_movements.py` |
| realizado: "hoje" | replica em payment/competence/due | `test_transaction_dates.py` |
| `list_transactions(status="actual")` | sem previstos na lista | `test_planned_transactions.py` |
| parcelado: valor é total ou parcela | pergunta `installment_amount_basis` | `test_installments.py` |
| parcela 180 de 360 | cria só 180…360 | `test_installments.py` |
| `*despesa*` no chat | `<strong>despesa</strong>` | `test_chat_format.py` |

## Imports comuns

```python
from app.agent.runner import process_message
from app.schemas import ToolCall
from app.services.intents import wants_list_accounts, wants_transfer
from app.services.tools import try_rule_based_parse
```

## Transferências

```python
from app.schemas import RegisterTransferInput, SummaryInput
from app.services import finance

# Par criado, saldos OK, período sem receita/despesa
finance.register_transfer(db, user_id, RegisterTransferInput(...))
summary = finance.get_summary(db, user_id, SummaryInput(ref_date=date.today()))
assert summary["income_cents"] == 0
assert summary["expense_cents"] == 0
```

## pytest-asyncio

`process_message` é `async def` — usar `@pytest.mark.asyncio`.
