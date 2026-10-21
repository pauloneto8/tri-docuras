import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:tri_docuras/account/account_controller.dart';
import 'package:tri_docuras/account/account_scope.dart';
import 'package:tri_docuras/account/auth_token.dart';
import 'package:tri_docuras/cart/cart_controller.dart';
import 'package:tri_docuras/cart/cart_item.dart';
import 'package:tri_docuras/cart/cart_scope.dart';
import 'package:tri_docuras/models/product.dart';
import 'package:tri_docuras/screens/checkout_screen.dart';
import 'package:tri_docuras/services/api_service.dart';
import 'package:tri_docuras/widgets/td_button.dart';

const _product = Product(
  id: 4,
  name: 'Brownie Tradicional',
  description: 'Teste',
  price: 12,
  featured: true,
  category: 'brownies',
);

/// Botão "Gerar Pix": `onPressed` nulo quer dizer desabilitado.
TdButton _payButton(WidgetTester tester) {
  return tester.widget<TdButton>(
    find.ancestor(
      of: find.text('Gerar Pix'),
      matching: find.byType(TdButton),
    ),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
    AuthToken.value = 'token-teste';
    AuthToken.onUnauthorized = null;
  });

  tearDown(() {
    AuthToken.value = null;
    AuthToken.onUnauthorized = null;
  });

  Future<List<http.Request>> pumpCheckout(
    WidgetTester tester, {
    required http.Response Function(http.Request) respond,
  }) async {
    tester.view.physicalSize = const Size(390 * 2.0, 844 * 2.0);
    tester.view.devicePixelRatio = 2.0;
    addTearDown(tester.view.reset);

    final sent = <http.Request>[];
    final client = MockClient((request) async {
      sent.add(request);
      return respond(request);
    });

    final cart = CartController()
      ..add(const CartItem(product: _product, quantity: 1));
    final account = AccountController(api: ApiService(client: client));

    await tester.pumpWidget(
      MaterialApp(
        home: CartScope(
          notifier: cart,
          child: AccountScope(
            notifier: account,
            child: Scaffold(
              body: CheckoutScreen(api: ApiService(client: client)),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    return sent;
  }

  Future<void> fillValidContact(WidgetTester tester) async {
    await tester.enterText(
      find.widgetWithText(TextField, 'Seu nome completo'),
      'Maria Silva',
    );
    await tester.enterText(
      find.widgetWithText(TextField, '(11) 91234-5678'),
      '81991234567',
    );
    await tester.pump();
  }

  testWidgets('Gerar Pix fica desabilitado sem o aceite, mesmo com dados válidos',
      (tester) async {
    await pumpCheckout(
      tester,
      respond: (_) => http.Response('{}', 500),
    );

    await fillValidContact(tester);

    expect(_payButton(tester).onPressed, isNull);
  });

  testWidgets('marcar o aceite libera o botão e o pedido leva accepted_terms',
      (tester) async {
    final sent = await pumpCheckout(
      tester,
      respond: (_) => http.Response(
        jsonEncode({'error': 'teste'}),
        400,
        headers: {'content-type': 'application/json'},
      ),
    );

    await tester.tap(find.byType(Checkbox));
    await tester.pump();

    await fillValidContact(tester);

    expect(_payButton(tester).onPressed, isNotNull);

    await tester.tap(find.text('Gerar Pix'));
    await tester.pumpAndSettle();

    final orders = sent.where((r) => r.url.path == '/api/orders');
    expect(orders, hasLength(1));
    final body = jsonDecode(orders.single.body) as Map<String, dynamic>;
    expect(body['accepted_terms'], isTrue);
    expect(body['items'], hasLength(1));
  });
}
