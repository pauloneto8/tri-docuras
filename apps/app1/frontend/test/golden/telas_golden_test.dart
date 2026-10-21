import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:tri_docuras/account/account_controller.dart';
import 'package:tri_docuras/account/account_scope.dart';
import 'package:tri_docuras/account/auth_token.dart';
import 'package:tri_docuras/cart/cart_controller.dart';
import 'package:tri_docuras/cart/cart_scope.dart';
import 'package:tri_docuras/favorites/favorites_controller.dart';
import 'package:tri_docuras/favorites/favorites_scope.dart';
import 'package:tri_docuras/orders/order_history_controller.dart';
import 'package:tri_docuras/orders/order_history_scope.dart';
import 'package:tri_docuras/screens/home_screen.dart';
import 'package:tri_docuras/services/api_service.dart';

// Os goldens são gerados e comparados no mesmo SDK do CI (Linux). Para
// atualizar uma tela de propósito: flutter test --update-goldens test/golden
//
// Fontes: sem busca na rede. Poppins aparece com as letras reais. Os títulos
// em Lora e os ícones do Material saem como caixas nestes goldens (limitação
// conhecida: o carregamento dessas fontes no teste não casou com o google_fonts).
// O golden ainda cobre posição, tamanho e cor de cada bloco da tela.
// Testes de regressão visual, não de conteúdo: os dados são fixos.

final _products = {
  'products': [
    {
      'id': 1,
      'name': 'Brownie Tradicional',
      'description': 'Brownie amanteigado clássico.',
      'price': 12.0,
      'featured': true,
      'category': 'brownies',
      'available': true,
      'stock': null,
      'options': [],
    },
    {
      'id': 2,
      'name': 'Ninho c/ Nutella',
      'description': 'Com recheio de Nutella.',
      'price': 14.0,
      'featured': false,
      'category': 'brownies',
      'available': true,
      'stock': null,
      'options': [],
    },
  ],
};

/// Carrega as fontes do app (assets/fonts) com os nomes de família que o
/// google_fonts usa quando não busca na rede: sem isso, o Flutter desenha
/// blocos (fonte Ahem) no lugar das letras.
Future<void> _loadAppFonts() async {
  const families = {
    'Poppins_regular': 'Poppins-Regular.ttf',
    'Poppins_500': 'Poppins-Medium.ttf',
    'Poppins_600': 'Poppins-SemiBold.ttf',
    'Poppins_700': 'Poppins-SemiBold.ttf',
    'Poppins': 'Poppins-Regular.ttf',
    'Lora_regular': 'Lora-SemiBold.ttf',
    'Lora_500': 'Lora-SemiBold.ttf',
    'Lora_600': 'Lora-SemiBold.ttf',
    'Lora_700': 'Lora-SemiBold.ttf',
    'Lora': 'Lora-SemiBold.ttf',
  };
  for (final entry in families.entries) {
    final loader = FontLoader(entry.key)
      ..addFont(rootBundle.load('assets/fonts/${entry.value}'));
    await loader.load();
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    GoogleFonts.config.allowRuntimeFetching = false;
    await _loadAppFonts();
  });

  setUp(() {
    SharedPreferences.setMockInitialValues({});
    AuthToken.value = null;
    AuthToken.onUnauthorized = null;
  });

  testWidgets('catálogo com produtos (celular)', (tester) async {
    tester.view.physicalSize = const Size(390 * 2.0, 844 * 2.0);
    tester.view.devicePixelRatio = 2.0;
    addTearDown(tester.view.reset);

    final client = MockClient(
      (request) async => http.Response(
        jsonEncode(_products),
        200,
        headers: {'content-type': 'application/json'},
      ),
    );
    final api = ApiService(client: client);

    await tester.pumpWidget(
      MaterialApp(
        home: CartScope(
          notifier: CartController(),
          child: FavoritesScope(
            notifier: FavoritesController(),
            child: OrderHistoryScope(
              notifier: OrderHistoryController(),
              child: AccountScope(
                notifier: AccountController(api: api),
                child: Scaffold(body: HomeScreen(api: api)),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await expectLater(
      find.byType(HomeScreen),
      matchesGoldenFile('goldens/home_catalogo.png'),
    );
  });
}
