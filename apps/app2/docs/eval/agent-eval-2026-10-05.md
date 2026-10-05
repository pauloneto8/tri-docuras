# Eval do agente v2 — 2026-10-05 (1ª medição, free tier do Groq)

**Status:** 5 de 83 casos medidos (offsets 0-4). O critério do plano segue sem
veredito: o free tier não comporta o lote. O 2º lote achou um defeito real de
prompt (receita não era mapeada para `register_income`), corrigido e aguardando
remedição. Medições em `docs/eval/`.

## Modelo e método

- Modelo do agente: `openai/gpt-oss-20b` (o `gpt-oss-120b`, que é o modelo de
  produção, estava com o orçamento do dia esgotado).
- `python -m app.scripts.agent_eval --mode both --limit 1 --offset <i>`, caso a
  caso, com `--delay 45`, usuário 1 (`pauloneto8@gmail.com`), container
  descartável com o código montado.
- Sem escrita no banco: o v2 só gera plano pendente e o legado só resolve a
  intenção.

## Custo medido (o achado principal)

| Medida | Valor |
|---|---|
| Payload do v2 só no prompt (31 ferramentas + prompt dinâmico) | ~2.800 tokens por chamada |
| Tokens por caso do v2 (2-4 chamadas) + legado | **12.218** (`simples_expense`) / **12.119** (`simples_expense_hoje`) |
| Dentre eles, prompt | 11.388 (93%) |
| Free tier do Groq | 200.000 tokens/dia **por modelo** + 8.000/min |

Consequências, todas medidas e não estimadas:

1. **Uma mensagem do agente custa ~12.000 tokens.** O free tier sustenta ~16
   mensagens por dia se nada mais usar o modelo.
2. **O orçamento é janela móvel, não relógio:** às 06:29 o contador estava em
   `Used 199091 / Limit 200000` e às 07:00 o mesmo modelo aceitou nova chamada
   sem trocar nada. Ele se recupera sozinho ao ritmo de ~140 tokens/min
   (~8.300/h) — ou seja, **um caso novo de 12k tokens leva ~85 min de
   orçamento acumulado**.
3. **O eval completo precisa de ~1.000.000 tokens** (83 casos × 12k) = **5 dias
   do orçamento inteiro**, sem nenhuma mensagem de chat no meio. Não é
   viável no planofree como "rodar e esperar".
4. O limite é **por modelo**: a chave free tem 11 modelos, e `gpt-oss-120b`,
   `gpt-oss-20b` e `qwen/qwen3.8-27b` têm orçamento próprio. Dá para separar
   carga (ex.: chat num modelo, eval em outro) — foi assim que este lote rodou
   no `20b` enquanto a produção segue no `120b`.
5. LLM local não é opção nesta máquina: 2 vCPU, 3 GB de RAM (1 GB livre), sem
   GPU, dividindo app1 + app2 + 2 Postgres.

## Resultado dos 2 casos medidos

| Caso | v2 | legado | Observação |
|---|---|---|---|
| `simples_expense` — "gastei 35,50 no mercado ontem" | ✅ | ✅ | 12.218 tokens |
| `simples_expense_hoje` — "paguei 12 reais de café hoje" | ⚠️ falso negativo | ✅ | v2 acertou a ferramenta e todos os argumentos; o matcher comparava `"12.00"` com `"12"` como texto |

Nenhum caso 3 em diante foi medido: o orçamento diário do modelo acabou no meio
do caso `simples_income` e a tentativa seguinte já era 429 por TPD.

## 2º lote (offsets 2-4) — receita não existia para o v2

`--offset 2 --limit 8`, 17:48-18:25, `gpt-oss-20b`, `--delay 45`. Mediu 3 casos
e parou no 4º (TPD); o legado não foi medido (ver "Correção do próprio eval").

| Caso | v2 | O que aconteceu |
|---|---|---|
| `simples_income` — "recebi 3000 de salário" | ❌ | `chamadas=[]`: respondeu em texto e caiu no fallback anti-inventar valor |
| `simples_income_freela` — "entrou 850 de freela no pix" | ❌ | chamou só `categorize`, nunca `register_income` |
| `previsto_despesa` — "vou gastar 200 de luz mês que vem" | ❌ | `chamadas=[]` |

### Causa (não é caso mal escrito)

Os três casos do YAML estão certos. A assimetria estava no prompt e no
toolkit, não nos casos:

- `register_expense` tinha descrição rica ("conta ou cartão; à vista, fixo ou
  parcelado; previsto ou realizado"); `register_income` era só "Novo lançamento
  de receita.";
- o bloco de regras do `prompt_v2.py` mapeava verbo → ferramenta **só para
  despesa** ("gastei/paguei/comprei" = despesa, "vou/pretendo" = previsto). Não
  havia nenhuma linha dizendo que "recebi/entrou/ganhei" é receita.

O modelo pequeno, sem essa pista, respondia em texto (e a guarda anti-alucinação
de valores zerava as chamadas) ou ia direto na `categorize`.

### Correção aplicada (aguardando remedição)

1. `app/agent/toolkit.py`: `register_income` agora diz que é para usar quando o
   usuário diz que recebeu/entrou/ganhou/foi creditado (salário, freela, vale
   refeição, reembolso, entrada, pix recebido).
2. `app/agent/prompt_v2.py`: nova regra "recebi/entrou/ganhei/foi creditado" =
   receita em `register_income`; transferência só quando o dinheiro sai de uma
   conta do próprio usuário para outra (mesma distinção que o legado faz em
   `runner.py::_resolve_intent`, receita antes de despesa).

**Antes de mexer em qualquer outra coisa, remedir os offsets 2-4** com o prompt
novo: se os 3 passarem, o defeito era de instrução; se continuarem igual, é
limitação do modelo de 20b e a medição tem de ser refeita no 120b (produção).

## Correção de calibração do próprio eval

Duas correções no medidor, nenhuma em `cases.yaml`:

1. `_as_number` normaliza `12`, `"12"`, `"12.00"`, `"R$ 12,00"` antes de
   comparar — o acerto do v2 no `simples_expense_hoje` era contado como errado.
2. **Fase legada não roda com o orçamento diário esgotado.** O legado também
   chama o Groq (`call_intent_llm`) e engole o 429 devolvendo "nenhuma
   ferramenta": medindo assim, todo caso virava falha do legado e o v2 parecia
   melhor por acidente (foi o que aconteceu no 2º lote, antes da correção). Agora
   `run()` marca `out_of_budget` e imprime "Legado não medido" em vez de
   inventar taxa — comparar v2 com um legado medido em janela vazia é pior do que
   não comparar.

## Como rodar o lote sem perder a saída

`docker compose run ... &` com o cliente morto (timeout de shell, reboot) perde
tudo: o container segue rodando e, com `--rm`, some junto com os logs.use
`-d` **sem** `--rm`, com nome, e leia com `docker logs`:

```bash
cd /opt/hosting
docker compose run -d --name eval-lote --no-deps \
  -e PYTHONPATH=/app -e PYTHONUNBUFFERED=1 -e GROQ_MODEL=openai/gpt-oss-20b \
  -v "$PWD/apps/app2:/app" -v /tmp/opencode:/lote \
  --entrypoint python app2 /lote/eval_lote.py <offset> <limit> <delay>

docker logs -f eval-lote      # acompanha
docker rm -f eval-lote       # no fim (--rm não pode estar, senão o log vai junto)
```

`eval_lote.py` e `eval_driver.py` (contagem de tokens por caso) ficam em
`/tmp/opencode`; sem `-e PYTHONPATH=/app` o script não acha o pacote `app`, e
sem `-e PYTHONUNBUFFERED=1` a saída fica em buffer e o log só aparece no fim.

## Como seguir

O critério do plano (v2 ≥ legado e ≥ 90%) **não pode ser avaliado hoje** no
free tier. Duas saídas, ambas com custo zero de código:

1. **Lotes diários pequenos** (o que o usuário aprovou): 1-2 casos a cada ~90
   min, com o script parando sozinho quando o TPD acaba. 83 casos ≈ 5 dias de
   orçamento — e o chat precisa de ~12k por mensagem, então convém reservar
   o modelo `gpt-oss-120b` para o chat e medir no `20b`.
2. **Upgrade para o Dev Tier** do Groq: resolve o eval inteiro em uma hora e
   tira o chat do risco de cair no legado.

## Comandos

```bash
# um caso (índice no YAML, 0-based), medindo tokens
cd /opt/hosting
docker compose run --rm --no-deps -T -e GROQ_MODEL=openai/gpt-oss-20b \
  -v "$PWD/apps/app2:/app" --entrypoint python app2 \
  -m app.scripts.agent_eval --mode both --limit 1 --offset 0 --delay 45

# um lote de 15 (para quando houver orçamento)
docker compose run --rm --no-deps -T -e GROQ_MODEL=openai/gpt-oss-20b \
  -v "$PWD/apps/app2:/app" --entrypoint python app2 \
  -m app.scripts.agent_eval --mode both --offset 0 --limit 15 --delay 45
```

Ordem sugerida dos lotes (por tema, para os primeiros dias renderem leitura de
vários blocos): offsets 0, 15, 30, 45, 60 e 75 — os 15 primeiros casos de cada
bloco. Sem deslocamento, os últimos índices (83) são o resto.

Fila em ordem para os próximos dias:

1. `--offset 2 --limit 3` — remedir `simples_income`, `simples_income_freela` e
   `previsto_despesa` com o prompt corrigido (antes/depois do defeito).
2. `--offset 5 --limit 10` — completa o bloco 1 (cases 0-14).
3. Depois: blocos 15, 30, 45, 60 e 75, 15 casos por dia no máximo.