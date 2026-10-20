import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:tri_docuras/account/auth_token.dart';
import 'package:tri_docuras/favorites/favorites_controller.dart';
import 'package:tri_docuras/services/api_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
    AuthToken.value = null;
  });

  tearDown(() => AuthToken.value = null);

  test('sem conta, favoritos ficam no aparelho', () async {
    final favorites = FavoritesController(api: ApiService(client: MockClient((_) async => fail('não deve chamar a API'))));

    await favorites.toggle(4);
    await favorites.load(force: true);

    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getStringList('favorite_product_ids'), ['4']);
    expect(favorites.isFavorite(4), isTrue);
  });

  test('ao entrar, favoritos do aparelho se juntam aos da conta e saem do aparelho',
      () async {
    SharedPreferences.setMockInitialValues({
      'favorite_product_ids': ['4'],
    });
    AuthToken.value = 'tok-1';
    Map<String, dynamic>? saved;
    final api = ApiService(
      client: MockClient((request) async {
        if (request.method == 'GET') {
          return http.Response(jsonEncode({'product_ids': [2]}), 200);
        }
        saved = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(jsonEncode({'product_ids': saved!['product_ids']}), 200);
      }),
    );
    final favorites = FavoritesController(api: api);

    await favorites.load(force: true);

    expect(favorites.ids, {2, 4});
    expect(saved?['product_ids'], containsAll([2, 4]));
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getStringList('favorite_product_ids'), isNull);
  });

  test('com conta, alterar favorito envia a lista inteira para a API', () async {
    AuthToken.value = 'tok-1';
    Map<String, dynamic>? sent;
    final api = ApiService(
      client: MockClient((request) async {
        if (request.method == 'GET') {
          return http.Response(jsonEncode({'product_ids': <int>[]}), 200);
        }
        sent = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(jsonEncode({'product_ids': sent!['product_ids']}), 200);
      }),
    );
    final favorites = FavoritesController(api: api);
    await favorites.load(force: true);

    await favorites.toggle(3);

    expect(sent?['product_ids'], [3]);
  });
}
