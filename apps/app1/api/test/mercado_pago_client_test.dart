import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:test/test.dart';
import 'package:tri_docuras_api/mercado_pago_client.dart';

void main() {
  group('mercadoPagoStatusIsPaid', () {
    test('approved é pago', () {
      expect(mercadoPagoStatusIsPaid('approved'), isTrue);
    });

    test('pending não é pago', () {
      expect(mercadoPagoStatusIsPaid('pending'), isFalse);
    });
  });

  group('buildPixBody', () {
    Map<String, Object?> body({String? email}) => MercadoPagoClient.buildPixBody(
          orderPublicId: 'TD-0042',
          amount: 24,
          customerName: 'Maria da Silva',
          whatsapp: '81991234567',
          payerEmail: email,
          items: const [
            PixItem(
              productId: 4,
              title: 'Brownie Tradicional (9x9cm)',
              quantity: 2,
              unitPrice: 12,
            ),
          ],
          notificationUrl: 'https://tridocuras.com.br/api/webhooks/mercadopago',
          expiresAt: DateTime.utc(2026, 10, 21, 12),
        );

    test('usa o e-mail real da conta e manda telefone e itens', () {
      final b = body(email: ' maria@exemplo.com ');
      final payer = b['payer']! as Map<String, Object?>;
      expect(payer['email'], 'maria@exemplo.com');
      expect(payer['first_name'], 'Maria');
      expect(payer['last_name'], 'da Silva');

      final info = b['additional_info']! as Map<String, Object?>;
      final items = info['items']! as List<Object?>;
      expect(items.single, {
        'id': '4',
        'title': 'Brownie Tradicional (9x9cm)',
        'quantity': 2,
        'unit_price': 12.0,
      });
      final infoPayer = info['payer']! as Map<String, Object?>;
      expect(infoPayer['phone'], {'area_code': '81', 'number': '991234567'});
    });

    test('sem conta, mantém o e-mail sintético do pedido', () {
      final payer = body()['payer']! as Map<String, Object?>;
      expect(payer['email'], 'pedido+td0042+81991234567@pagador.tridocuras.com.br');
    });
  });

  group('mercadoPagoStatusIsRejected', () {
    test('rejected é recusa; pending e approved não são', () {
      expect(mercadoPagoStatusIsRejected('rejected'), isTrue);
      expect(mercadoPagoStatusIsRejected(' Rejected '), isTrue);
      expect(mercadoPagoStatusIsRejected('pending'), isFalse);
      expect(mercadoPagoStatusIsRejected('approved'), isFalse);
      expect(mercadoPagoStatusIsRejected(null), isFalse);
    });
  });

  group('createPixPayment', () {
    Map<String, Object?> pixResponse() => {
          'id': 555,
          'status': 'pending',
          'date_of_expiration': '2026-10-21T12:10:00.000-03:00',
          'point_of_interaction': {
            'transaction_data': {'qr_code': 'COPIA-E-COLA', 'qr_code_base64': 'UVI='},
          },
        };

    test('manda e-mail real e itens na primeira tentativa', () async {
      final bodies = <Map<String, dynamic>>[];
      final mp = MercadoPagoClient(
        accessToken: 'tok',
        client: MockClient((request) async {
          bodies.add(jsonDecode(request.body) as Map<String, dynamic>);
          return http.Response(jsonEncode(pixResponse()), 201);
        }),
      );

      final pix = await mp.createPixPayment(
        orderPublicId: 'TD-0042',
        amount: 12,
        customerName: 'Maria Silva',
        whatsapp: '81991234567',
        payerEmail: 'maria@exemplo.com',
        items: const [
          PixItem(productId: 4, title: 'Brownie', quantity: 1, unitPrice: 12),
        ],
      );

      expect(pix.copyCode, 'COPIA-E-COLA');
      expect(bodies, hasLength(1));
      expect(bodies.single['payer']['email'], 'maria@exemplo.com');
      expect(bodies.single['additional_info']['items'], hasLength(1));
    });

    test('se o Mercado Pago recusar os dados extras (400), tenta sem eles',
        () async {
      final bodies = <Map<String, dynamic>>[];
      final keys = <String?>[];
      final mp = MercadoPagoClient(
        accessToken: 'tok',
        client: MockClient((request) async {
          bodies.add(jsonDecode(request.body) as Map<String, dynamic>);
          keys.add(request.headers['X-Idempotency-Key']);
          if (bodies.length == 1) {
            return http.Response(
              jsonEncode({'message': 'invalid additional_info'}),
              400,
            );
          }
          return http.Response(jsonEncode(pixResponse()), 201);
        }),
      );

      final pix = await mp.createPixPayment(
        orderPublicId: 'TD-0043',
        amount: 12,
        customerName: 'Maria Silva',
        whatsapp: '81991234567',
        payerEmail: 'maria@exemplo.com',
      );

      expect(pix.paymentId, 555);
      expect(bodies, hasLength(2));
      expect(bodies.first.containsKey('additional_info'), isTrue);
      expect(bodies.last.containsKey('additional_info'), isFalse);
      expect(bodies.last['payer']['email'], 'maria@exemplo.com');
      expect(keys.first, isNot(keys.last));
    });
  });
}
