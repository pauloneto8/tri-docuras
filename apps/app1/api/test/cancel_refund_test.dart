import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:test/test.dart';
import 'package:tri_docuras_api/admin_orders.dart';
import 'package:tri_docuras_api/mercado_pago_client.dart';

void main() {
  group('cancelRefundPlan', () {
    test('pedido não pago não precisa de estorno, com ou sem escolha', () {
      expect(cancelRefundPlan('pending_payment', null),
          CancelRefundPlan.notNeeded);
      expect(cancelRefundPlan('pending_payment', true),
          CancelRefundPlan.notNeeded);
    });

    test('pedido pago exige escolha explícita', () {
      for (final status in ['paid', 'preparing', 'ready']) {
        expect(
          () => cancelRefundPlan(status, null),
          throwsA(isA<AdminOrderException>()),
        );
      }
    });

    test('escolha de estornar ou não para pedido pago', () {
      expect(cancelRefundPlan('paid', true), CancelRefundPlan.refund);
      expect(cancelRefundPlan('ready', false), CancelRefundPlan.skipRefund);
    });
  });

  group('refundLabel', () {
    test('rótulos do painel', () {
      expect(refundLabel('refunded'), 'Estornado');
      expect(refundLabel('pending_refund'), 'Estorno em análise');
      expect(refundLabel('not_refunded'), 'Cancelado sem estorno');
      expect(refundLabel(null), isNull);
    });
  });

  group('MercadoPagoClient.refundPayment', () {
    test('envia POST no pagamento com chave de idempotência', () async {
      late http.Request sent;
      final client = MockClient((request) async {
        sent = request;
        return http.Response(
          jsonEncode({'id': 987, 'status': 'approved'}),
          201,
        );
      });

      final mp = MercadoPagoClient(client: client, accessToken: 'tok');
      final data = await mp.refundPayment(
        123,
        idempotencyKey: 'refund-TD-1',
      );

      expect(sent.method, 'POST');
      expect(sent.url.toString(),
          'https://api.mercadopago.com/v1/payments/123/refunds');
      expect(sent.headers['Authorization'], 'Bearer tok');
      expect(sent.headers['X-Idempotency-Key'], 'refund-TD-1');
      expect(data['status'], 'approved');
    });

    test('erro do MP vira MercadoPagoException com a mensagem dele', () async {
      final client = MockClient((_) async => http.Response(
            jsonEncode({'message': 'Payment already refunded'}),
            400,
          ));
      final mp = MercadoPagoClient(client: client, accessToken: 'tok');

      expect(
        () => mp.refundPayment(123, idempotencyKey: 'k'),
        throwsA(
          isA<MercadoPagoException>().having(
            (e) => e.message,
            'message',
            'Payment already refunded',
          ),
        ),
      );
    });

    test('sem credencial não chama o MP', () {
      final mp = MercadoPagoClient(
        client: MockClient((_) async => fail('não deveria chamar')),
        accessToken: null,
      );
      expect(
        () => mp.refundPayment(123, idempotencyKey: 'k'),
        throwsA(isA<MercadoPagoException>()),
      );
    });
  });
}
