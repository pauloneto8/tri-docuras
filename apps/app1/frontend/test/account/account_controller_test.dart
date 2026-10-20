import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:tri_docuras/account/account_controller.dart';
import 'package:tri_docuras/account/auth_token.dart';
import 'package:tri_docuras/services/api_service.dart';

const _customerJson = {
  'id': 7,
  'email': 'ana@exemplo.com',
  'name': 'Ana Lima',
  'whatsapp': '81996918192',
  'addresses': [],
};

AccountController _controller(http.Client client) {
  return AccountController(api: ApiService(client: client));
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
    AuthToken.value = null;
    AuthToken.onUnauthorized = null;
  });

  tearDown(() {
    AuthToken.value = null;
    AuthToken.onUnauthorized = null;
  });

  test('login guarda o token na sessão e no aparelho', () async {
    final client = MockClient((request) async {
      expect(request.url.path, '/api/customers/session');
      return http.Response(
        jsonEncode({'token': 'tok-1', 'customer': _customerJson}),
        200,
      );
    });
    final account = _controller(client);

    await account.login(email: 'ana@exemplo.com', password: 'senha-boa-1');

    expect(account.isLoggedIn, isTrue);
    expect(account.profile?.name, 'Ana Lima');
    expect(AuthToken.value, 'tok-1');
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('customer_token'), 'tok-1');
  });

  test('logout limpa sessão e token salvo', () async {
    final client = MockClient((_) async => http.Response(
          jsonEncode({'token': 'tok-1', 'customer': _customerJson}),
          200,
        ));
    final account = _controller(client);
    await account.login(email: 'ana@exemplo.com', password: 'senha-boa-1');

    await account.logout();

    expect(account.isLoggedIn, isFalse);
    expect(account.profile, isNull);
    expect(AuthToken.value, isNull);
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('customer_token'), isNull);
  });

  test('load restaura a sessão salva e manda o token na busca do perfil',
      () async {
    SharedPreferences.setMockInitialValues({'customer_token': 'tok-salvo'});
    String? sentAuth;
    final client = MockClient((request) async {
      sentAuth = request.headers['Authorization'];
      return http.Response(jsonEncode({'customer': _customerJson}), 200);
    });
    final account = _controller(client);

    await account.load();

    expect(sentAuth, 'Bearer tok-salvo');
    expect(account.isLoggedIn, isTrue);
    expect(account.profile?.email, 'ana@exemplo.com');
  });

  test('token recusado pela API (401) encerra a sessão', () async {
    SharedPreferences.setMockInitialValues({'customer_token': 'tok-velho'});
    final client = MockClient((_) async => http.Response(
          jsonEncode({'error': 'Entre na sua conta para continuar.'}),
          401,
        ));
    final account = _controller(client);

    await account.load();

    expect(account.isLoggedIn, isFalse);
    expect(AuthToken.value, isNull);
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('customer_token'), isNull);
  });

  test('queda de rede ao restaurar mantém o token para tentar depois',
      () async {
    SharedPreferences.setMockInitialValues({'customer_token': 'tok-salvo'});
    final client = MockClient((_) async => throw http.ClientException('offline'));
    final account = _controller(client);

    await account.load();

    expect(AuthToken.value, 'tok-salvo');
    expect(account.profile, isNull);
  });

  test('troca de senha substitui o token pelo novo', () async {
    final client = MockClient((request) async {
      if (request.url.path == '/api/customers/me/password') {
        return http.Response(jsonEncode({'token': 'tok-novo'}), 200);
      }
      return http.Response(
        jsonEncode({'token': 'tok-antigo', 'customer': _customerJson}),
        200,
      );
    });
    final account = _controller(client);
    await account.login(email: 'ana@exemplo.com', password: 'senha-boa-1');

    await account.changePassword(
      currentPassword: 'senha-boa-1',
      newPassword: 'senha-nova-2',
    );

    expect(AuthToken.value, 'tok-novo');
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('customer_token'), 'tok-novo');
  });

  test('onSessionChanged dispara ao entrar e ao sair', () async {
    var calls = 0;
    final client = MockClient((_) async => http.Response(
          jsonEncode({'token': 'tok-1', 'customer': _customerJson}),
          200,
        ));
    final account = AccountController(
      api: ApiService(client: client),
      onSessionChanged: () => calls++,
    );

    await account.login(email: 'ana@exemplo.com', password: 'senha-boa-1');
    await account.logout();

    expect(calls, 2);
  });
}
