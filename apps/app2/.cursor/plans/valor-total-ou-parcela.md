# Plano pendente: valor total da compra vs valor da parcela

**Status:** implementado (2026-09-02)  
**Workspace:** `/opt/hosting/apps/app2`  
**Origem:** pedido do usuário — quando o assistente já tem um valor e o lançamento é parcelado, perguntar se aquele valor é o **total da compra** (dividir por N) ou o **valor de cada parcela** (repetir N vezes). Escopo escolhido: **chat e formulário de Movimentos**.  
**Cópia Cursor:** `/root/.cursor/plans/valor_total_ou_parcela_0ef3ea11.plan.md`

Antes de editar: `move_agent_to_root` → `/opt/hosting/apps/app2`.  
Ler: `.cursor/skills/assistfin-installments/SKILL.md`, `.cursor/skills/assistfin-ai-agent/SKILL.md`, `.cursor/skills/assistfin-implementation/SKILL.md`.  
Responder em **português**.

---

## Objetivo

Hoje `amount` no parcelamento é **sempre o total**: `split_cents(total, N)` em [`app/services/installments.py`](../../app/services/installments.py). O prompt do LLM (regra 23) afirma “O amount e o valor TOTAL”.

Passar a **perguntar sempre** (não inferir por “12x” / “parcela de…”):

| Escolha | Significado | Parcelas geradas | `installment_plans.total_cents` |
|---------|-------------|------------------|----------------------------------|
| `total` | Valor da compra inteira | `split_cents(amount, N)` (resto na última) | = `amount` |
| `installment` | Valor de **cada** parcela | N vezes o mesmo `amount` | = `amount * N` |

Exemplo: usuário disse **R$ 1.200,00** em **12x**.

- Total → 12 parcelas ~ R$ 100,00 (resto de 1 centavo na última se não dividir exato).
- Parcela → 12 parcelas de R$ 1.200,00; total do plano R$ 14.400,00.

A pergunta deve **mostrar essa conta** para o usuário não errar.

---

## Fora de escopo

- Sem migração de banco (não precisa coluna nova em `installment_plans`; `total_cents` já existe).
- Transferências e lançamento **fixo** não parcelam (continua mutuamente exclusivo).
- Não inferir basis pelo LLM nem por heurística de texto.
- Não misturar com o plano de visual do chat (`.cursor/plans/chat-visual-completo.md`).
- Realizar uma parcela (`realize_planned`) não muda: cada transação já tem o `amount_cents` certo.

---

## Arquivos a alterar

| Arquivo | O quê |
|---------|--------|
| [`app/services/installments.py`](../../app/services/installments.py) | `repeat_cents`; `create_installment_plan(..., amount_basis="total")` |
| [`app/schemas.py`](../../app/schemas.py) | `installment_amount_basis: Literal["total", "installment"] \| None` em `RegisterExpenseInput` e `RegisterIncomeInput` |
| [`app/services/finance.py`](../../app/services/finance.py) | `_register_installment_movement` e `create_user_transaction` passam o basis |
| [`app/services/transaction_slots.py`](../../app/services/transaction_slots.py) | Slot, `_next_slot`, `fill_slot`, `_tool_call_from_wizard`, pergunta com `format_brl` |
| [`app/services/transaction_wizard.py`](../../app/services/transaction_wizard.py) | Só se o slot novo precisar da mesma guarda que `INSTALLMENT_SLOTS` (já cobre se o frozenset incluir o nome) |
| [`app/services/agent_suggestions.py`](../../app/services/agent_suggestions.py) | Chips do slot |
| [`app/services/tools.py`](../../app/services/tools.py) | Texto de confirmação com total e valor de cada parcela |
| [`app/agent/prompt.py`](../../app/agent/prompt.py) | Regra 23: **não** dizer que amount é total; **não** enviar `installment_amount_basis` (wizard pergunta, como `status`) |
| [`app/templates/transactions.html`](../../app/templates/transactions.html) | Radios + hint JS em `#installment-options` |
| [`app/routers/pages.py`](../../app/routers/pages.py) | Form POST: `installment_amount_basis` → `create_user_transaction` |
| [`tests/test_installments.py`](../../tests/test_installments.py) | Motor, wizard, form |
| [`tests/test_agent_suggestions.py`](../../tests/test_agent_suggestions.py) | Chips do novo slot |
| Skill, [`AGENTS.md`](../../AGENTS.md), [`README.md`](../../README.md), [`docs/CHANGELOG.md`](../../docs/CHANGELOG.md), [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md) | Valor não é mais sempre total |

---

## Motor

```python
def repeat_cents(unit_cents: int, count: int) -> list[int]:
    if count < 2:
        raise ValueError("Parcelamento exige pelo menos 2 parcelas.")
    return [unit_cents] * count
```

Em `create_installment_plan`, parâmetro `amount_basis: Literal["total", "installment"] = "total"`:

- O argumento atual `total_cents` passa a significar **o valor informado pelo usuário em centavos** (total da compra **ou** valor da parcela, conforme o basis).
- `total` → `amounts = split_cents(total_cents, installment_count)`; `plan.total_cents = total_cents`
- `installment` → `amounts = repeat_cents(total_cents, installment_count)`; `plan.total_cents = total_cents * installment_count`

Default `total` só para não quebrar testes unitários de `split_cents` / registros antigos que não passam o campo. Wizard e form **devem enviar** o campo.

`_register_installment_movement`: ler `payload.installment_amount_basis or "total"` e repassar.

`create_user_transaction`: novo kwarg `installment_amount_basis` incluído no `common` dict que monta `RegisterExpenseInput` / `RegisterIncomeInput` (hoje linhas ~567–583).

---

## Wizard — slot `installment_amount_basis`

Valores: `"total"` | `"installment"`.

### `_next_slot`

Depois dos slots de parcela **e** do valor:

```
if payment_mode == installment:
    if not installment_count → installment_count
    if not installment_interval → installment_interval
if not amount → amount
if payment_mode == installment and not installment_amount_basis → installment_amount_basis
if not description → ...
```

Isso cobre:

1. Fluxo atual: modo → N → intervalo → valor → **basis** → descrição…
2. Valor já veio na mensagem (“gastei 1200”) e depois o usuário diz parcelado: assim que N existir, pergunta o basis.

Ao limpar parcelado (`payment_mode` → `single` / `fixed`), zerar também `installment_amount_basis` (junto de `installment_count` / `interval` em `fill_slot` de `payment_mode`).

### Pergunta

Não usar string estática só em `SLOT_QUESTIONS`. Gerar em `_question_for_slot` com `format_brl` (`app/schemas.py`):

- `amount` do wizard, `installment_count`
- `per_if_total` ≈ amount/N (pode usar `split_cents(decimal_to_cents(amount), N)[0]` formatado, ou divisão exibida “cerca de”)
- `total_if_unit` = amount × N

Texto alvo:

> Os **R$ 1.200,00** são o **valor total** da compra (12 parcelas de cerca de R$ 100,00) ou o **valor de cada parcela** (12 × R$ 1.200,00 = R$ 14.400,00)?

### Parse (`fill_slot`)

- total: `total`, `valor total`, `da compra`, `dividir`, chip `Valor total`
- parcela: `parcela`, `valor da parcela`, `cada parcela`, `da parcela`, chip `Valor da parcela`

Não tratar `não` como cancelamento global (o slot entra em `INSTALLMENT_SLOTS`).

```python
INSTALLMENT_SLOTS = frozenset({
    "installment_count",
    "installment_interval",
    "installment_amount_basis",
})
```

`is_slot_answer` deve aceitar as respostas acima (seguir o padrão dos outros slots).

### Chips

```python
if field == "installment_amount_basis":
    return _with_cancel(["Valor total", "Valor da parcela"])
```

### Tool call

Em `_tool_call_from_wizard`, se `payment_mode == "installment"`:

```python
args["installment_amount_basis"] = wizard["installment_amount_basis"]
```

Não copiar basis do LLM em `_wizard_from_tool_call` (deixar `None` para o wizard perguntar), igual `status`.

### Prompt

Regra 23 em `prompt.py`: manter extração de `installment_count` / `interval`; **apagar** “O amount e o valor TOTAL”; acrescentar que **não** envie `installment_amount_basis` (o sistema pergunta).

### Confirmação

`_format_installments` em `tools.py` hoje:

`Parcelado: {count}x {label} (valor total)`

Trocar para refletir o basis, por exemplo:

- total: `Parcelado: 12x mensal — total R$ 1.200,00 (cerca de R$ 100,00 cada)`
- installment: `Parcelado: 12x mensal — R$ 1.200,00 cada (total R$ 14.400,00)`

---

## Formulário Movimentos

Em `#installment-options` ([`transactions.html`](../../app/templates/transactions.html) ~linhas 247–258):

Radios `name="installment_amount_basis"`:

- `value="total"` — “Valor informado é o **total da compra** (divide nas parcelas)”
- `value="installment"` — “Valor informado é o **valor de cada parcela** (repete N vezes)”

Obrigatórios **somente** se `#is-installmented` estiver marcado (JS: `required` dinâmico, ou validar no POST).

Hint `#installment-basis-hint`: ao mudar valor, N, intervalo ou radio, atualizar texto:

- total: `R$ 1.200,00 ÷ 12 ≈ R$ 100,00 por parcela`
- installment: `12 × R$ 1.200,00 = R$ 14.400,00 no total`

POST em `pages.py` (`create_user_transaction` ~linha 432):

```python
installment_amount_basis: str | None = Form(None)
```

Se `inst_count` e não `installment_amount_basis` in `{"total", "installment"}` → `ValueError` claro. Passar o kwarg para `create_user_transaction`.

---

## Testes

[`tests/test_installments.py`](../../tests/test_installments.py):

1. `repeat_cents(10000, 12) == [10000] * 12`
2. Plano com `amount_basis="installment"`, unit 10000, N=12 → 12 transações com `amount_cents == 10000`; `plan.total_cents == 120000`
3. `amount_basis="total"` 10001 / 3 → `[3333, 3333, 3335]` (já existe `test_split_cents_remainder_on_last`; garantir o create_plan)
4. Wizard via `process_message`: após valor + “parcelado” + N + intervalo, `result.message` contém “total” e “parcela”; `result.suggestions` tem `Valor total` e `Valor da parcela`
5. Completar wizard com chip “Valor da parcela” e confirmar → N lançamentos iguais
6. Chip “Valor total” → split como hoje

Form (pode ser teste de `create_user_transaction` sem HTTP, ou POST se já houver padrão):

- `installment_count` sem basis → `ValueError`
- basis `installment` → parcelas iguais

Chips: `for_transaction_wizard_field("installment_amount_basis", ...)` em `test_agent_suggestions.py`.

---

## Docs a atualizar (na implementação)

- Skill `assistfin-installments`: regra “Valor informado = total” vira as duas opções + slot novo.
- `AGENTS.md` seção “Lançamentos parcelados”
- README tabela “Valor | Total informado ÷ N”
- `docs/ARCHITECTURE.md` e `docs/CHANGELOG.md` (Unreleased)

Após implementar, marcar este arquivo como **implementado** (data) e **remover** o item correspondente da lista “Planos pendentes” em `AGENTS.md`.

---

## Verificação

```bash
cd /opt/hosting
docker compose build app2
docker compose up -d app2
docker compose exec -T app2 python -m pytest -q
docker compose exec -T app2 python -m pytest tests/test_installments.py tests/test_agent_suggestions.py -q
```

Browser:

1. Chat: “gastei 1200 no notebook”, seguir wizard até parcelado 12x mensal → pergunta com as duas contas → **Valor da parcela** → confirmação mostra total R$ 14.400 → Confirmar → 12 lançamentos de R$ 1.200.
2. Mesmo fluxo com **Valor total** → ~R$ 100 cada.
3. Movimentos: marcar Parcelado, preencher valor/N, alternar radios e ver o hint; gravar cada modo.

---

## Critério de pronto

- Sem valor+parcelado o assistente **não** assume total.
- “Valor da parcela” replica o centavo informado em todas as N parcelas.
- “Valor total” continua `split_cents`.
- Form exige radio e grava o mesmo comportamento.
- Confirmação e hint mostram total **e** valor de cada parcela.
- pytest verde no container; fluxos conferidos no browser.
