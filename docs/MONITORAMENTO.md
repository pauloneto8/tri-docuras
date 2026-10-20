# Monitoramento da loja Tri Doçuras

## O que já está no código

- **`GET /api/health`** responde `200` com `status: ok` quando o banco
  responde, e `503` com `status: error` quando não responde.
- **Falhas do Mercado Pago e do webhook** saem no log do container
  `app-tridocuras`, sempre com o ID do pedido ou do pagamento:
  - `[mp] webhook rejeitado: assinatura inválida (data.id=...)`
  - `[mp] webhook: falha ao processar pagamento <id>: ...`
  - `[mp] Pix do pedido <TD-XXXX> não gerado: ...`
  - `[mp] estorno do pedido <TD-XXXX> falhou: ...`
  - `[mp] reconsulta do pedido <TD-XXXX> falhou: ...`

  Ver: `docker logs --since 1h app-tridocuras | grep '\[mp\]'`

## Uptime externo (configuração manual, faz o dono)

O alerta precisa de um serviço **fora da VPS**: se a VPS cair, ele precisa
continuar avisando. Sugestão: UptimeRobot (plano gratuito) ou BetterStack.

1. Criar uma conta com o e-mail do dono.
2. Novo monitor → tipo **Keyword**.
   - URL: `https://tridocuras.com.br/api/health`
   - Palavra-chave: `"database":"connected"` (falha se a API responder mas o
     banco estiver fora).
   - Intervalo: 5 minutos.
3. Contatos de alerta: e-mail do dono, e WhatsApp se o plano permitir.
4. Teste de aceite: parar o container de propósito por alguns minutos
   (`docker stop app-tridocuras`, com autorização), confirmar que o alerta
   chega, e subir de novo com `docker start app-tridocuras`.

## Limites conhecidos

- O webhook responde `200` mesmo quando falha, para o Mercado Pago não
  reenviar em loop. A falha fica só no log; a reconsulta do polling do app
  cobre o pedido. Não há alerta automático para isso ainda: é preciso
  olhar o log ou criar um alerta por busca no log.
