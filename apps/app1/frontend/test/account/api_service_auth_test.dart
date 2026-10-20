import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:tri_docuras/account/auth_token.dart';
import 'package:tri_docuras/cart/delivery_mode.dart';
import 'package:tri_docuras/checkout/checkout_draft.dart';
import 'package:tri_docuras/services/api_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  tearDown(() {
    AuthToken.value = null;
    AuthToken.onUnauthorized = null;
  });

  test('sem sessão, não envia Authorization', () async {
    AuthToken.value = null;
    String? auth = 'nao-foi-chamado';
    final api = ApiService(
      client: MockClient((request) async {
        auth = request.headers['Authorization'];
        return http.Response(
          jsonEncode({'order': {'id': 'TD-0001', 'status': 'paid', 'status_label': 'Pago', 'delivery_label': 'Retirada', 'total': 12, 'is_completed': false}, 'timeline': []}),
          200,
        );
      }),
    );

    await api.fetchOrderTracking('TD-0001');

    expect(auth, isNull);
  });

  test('com sessão, envia o token no rastreamento', () async {
    AuthToken.value = 'tok-42';
    String? auth;
    final api = ApiService(
      client: MockClient((request) async {
        auth = request.headers['Authorization'];
        return http.Response(
          jsonEncode({'order': {'id': 'TD-0001', 'status': 'paid', 'status_label': 'Pago', 'delivery_label': 'Retirada', 'total': 12, 'is_completed': false}, 'timeline': []}),
          200,
        );
      }),
    );

    await api.fetchOrderTracking('TD-0001');

    expect(auth, 'Bearer tok-42');
  });

  test('401 com sessão ativa avisa a sessão e marca o erro', () async {
    AuthToken.value = 'tok-velho';
    var notified = false;
    AuthToken.onUnauthorized = () => notified = true;
    final api = ApiService(
      client: MockClient((_) async => http.Response(
            jsonEncode({'error': 'Entre na sua conta para fazer um pedido.'}),
            401,
          )),
    );

    await expectLater(
      api.fetchOrderStatus('TD-0001'),
      throwsA(
        isA<ApiException>().having((e) => e.unauthorized, 'unauthorized', isTrue),
      ),
    );
    expect(notified, isTrue);
  });

  test('401 sem sessão mostra a mensagem da API, sem marcar expiração', () async {
    AuthToken.value = null;
    var notified = false;
    AuthToken.onUnauthorized = () => notified = true;
    final api = ApiService(
      client: MockClient((_) async => http.Response(
            jsonEncode({'error': 'Entre na sua conta para fazer um pedido.'}),
            401,
          )),
    );

    await expectLater(
      api.createOrder(
        draft: _draft(),
        items: const [],
      ),
      throwsA(
        isA<ApiException>()
            .having((e) => e.message, 'message', 'Entre na sua conta para fazer um pedido.')
            .having((e) => e.unauthorized, 'unauthorized', isFalse),
      ),
    );
    expect(notified, isFalse);
  });
}

CheckoutDraft _draft() => const CheckoutDraft(
      customerName: 'Ana Lima',
      whatsappDigits: '81996918192',
      total: 12,
      deliveryMode: DeliveryMode.pickup,
    );
